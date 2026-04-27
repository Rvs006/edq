"""Lightweight protocol observers for DHCP, DNS, and NTP evidence collection."""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import socket
import struct
import time
from typing import Any
from weakref import WeakKeyDictionary

from app.config import settings

logger = logging.getLogger("edq.protocol_observer")

_LOCKS: WeakKeyDictionary[asyncio.AbstractEventLoop, dict[str, asyncio.Lock]] = WeakKeyDictionary()
_NTP_EPOCH = 2208988800
_DHCP_MAGIC_COOKIE = b"\x63\x82\x53\x63"
_DHCP_MESSAGE_LABELS = {
    1: "discover",
    2: "offer",
    3: "request",
    4: "decline",
    5: "ack",
    6: "nak",
    7: "release",
    8: "inform",
}
_RUNTIME_FIELDS = {
    "enabled": "PROTOCOL_OBSERVER_ENABLED",
    "bind_host": "PROTOCOL_OBSERVER_BIND_HOST",
    "timeout_seconds": "PROTOCOL_OBSERVER_TIMEOUT_SECONDS",
    "dns_port": "PROTOCOL_OBSERVER_DNS_PORT",
    "ntp_port": "PROTOCOL_OBSERVER_NTP_PORT",
    "dhcp_port": "PROTOCOL_OBSERVER_DHCP_PORT",
    "dhcp_offer_ip": "PROTOCOL_OBSERVER_DHCP_OFFER_IP",
    "dhcp_subnet_mask": "PROTOCOL_OBSERVER_DHCP_SUBNET_MASK",
    "dhcp_router_ip": "PROTOCOL_OBSERVER_DHCP_ROUTER_IP",
    "dhcp_dns_server": "PROTOCOL_OBSERVER_DHCP_DNS_SERVER",
    "dhcp_lease_seconds": "PROTOCOL_OBSERVER_DHCP_LEASE_SECONDS",
}


def _observer_lock(name: str) -> asyncio.Lock:
    """Return a lock scoped to the current event loop.

    FastAPI request handlers, background tasks, and tests may run this module
    from different event loops. Reusing one module-level asyncio.Lock across
    those loops can raise immediately and make observer-backed tests look
    broken before their scanner fallback runs.
    """
    loop = asyncio.get_running_loop()
    loop_locks = _LOCKS.setdefault(loop, {})
    lock = loop_locks.get(name)
    if lock is None:
        lock = asyncio.Lock()
        loop_locks[name] = lock
    return lock


def current_protocol_observer_settings() -> dict[str, Any]:
    return {
        field: getattr(settings, setting_name)
        for field, setting_name in _RUNTIME_FIELDS.items()
    }


def apply_protocol_observer_settings(overrides: dict[str, Any]) -> dict[str, Any]:
    for field, setting_name in _RUNTIME_FIELDS.items():
        if field in overrides:
            setattr(settings, setting_name, overrides[field])
    return current_protocol_observer_settings()


def _local_ip_for_target(target_ip: str | None) -> str | None:
    if not target_ip:
        return None
    sock: socket.socket | None = None
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect((target_ip, 1))
        return str(sock.getsockname()[0])
    except OSError:
        return None
    finally:
        if sock is not None:
            sock.close()


def _bind_udp_socket(port: int) -> socket.socket:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind((settings.PROTOCOL_OBSERVER_BIND_HOST, port))
    sock.setblocking(False)
    return sock


def _decode_dns_name(packet: bytes, offset: int) -> tuple[str, int]:
    labels: list[str] = []
    while offset < len(packet):
        length = packet[offset]
        offset += 1
        if length == 0:
            break
        if offset + length > len(packet):
            raise ValueError("truncated DNS label")
        labels.append(packet[offset:offset + length].decode("ascii", errors="replace"))
        offset += length
    return ".".join(labels), offset


def parse_dns_query(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 12:
        return None
    txid, flags, qdcount, _, _, _ = struct.unpack("!HHHHHH", packet[:12])
    if flags & 0x8000:
        return None
    if qdcount < 1:
        return None
    name, offset = _decode_dns_name(packet, 12)
    if offset + 4 > len(packet):
        return None
    qtype, qclass = struct.unpack("!HH", packet[offset:offset + 4])
    return {
        "txid": txid,
        "flags": flags,
        "name": name,
        "qtype": qtype,
        "qclass": qclass,
        "question_end": offset + 4,
    }


def build_dns_response(packet: bytes, response_ip: str | None) -> bytes:
    query = parse_dns_query(packet)
    if query is None:
        return b""

    header = struct.pack(
        "!HHHHHH",
        query["txid"],
        0x8180,
        1,
        1 if response_ip and query["qtype"] == 1 else 0,
        0,
        0,
    )
    question = packet[12:query["question_end"]]
    if not response_ip or query["qtype"] != 1:
        return header + question

    answer = (
        b"\xc0\x0c"
        + struct.pack("!HHIH", query["qtype"], query["qclass"], 60, 4)
        + socket.inet_aton(response_ip)
    )
    return header + question + answer


def parse_ntp_request(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 48:
        return None
    first = packet[0]
    return {
        "version": (first >> 3) & 0x7,
        "mode": first & 0x7,
    }


def build_ntp_response(packet: bytes) -> bytes:
    parsed = parse_ntp_request(packet) or {"version": 4}
    version = parsed["version"] or 4
    mode = 4
    first = (0 << 6) | (version << 3) | mode
    now = time.time() + _NTP_EPOCH
    seconds = int(now)
    fraction = int((now - seconds) * (1 << 32))
    transmit = struct.pack("!II", seconds, fraction)
    response = bytearray(48)
    response[0] = first
    response[1] = 1
    response[2] = 6
    response[3] = 0xEC
    response[24:32] = packet[40:48] if len(packet) >= 48 else b"\x00" * 8
    response[32:40] = transmit
    response[40:48] = transmit
    return bytes(response)


def _mac_bytes_to_string(raw: bytes, hlen: int) -> str:
    return ":".join(f"{byte:02X}" for byte in raw[:hlen])


def _parse_dhcp_options(raw: bytes) -> dict[int, bytes]:
    options: dict[int, bytes] = {}
    index = 0
    while index < len(raw):
        code = raw[index]
        index += 1
        if code == 255:
            break
        if code == 0:
            continue
        if index >= len(raw):
            break
        length = raw[index]
        index += 1
        value = raw[index:index + length]
        index += length
        options[code] = value
    return options


def parse_dhcp_packet(packet: bytes) -> dict[str, Any] | None:
    if len(packet) < 240 or packet[236:240] != _DHCP_MAGIC_COOKIE:
        return None
    fields = struct.unpack("!BBBBIHH4s4s4s4s16s64s128s", packet[:236])
    options = _parse_dhcp_options(packet[240:])
    message_type = options.get(53, b"")
    requested_ip = options.get(50, b"")
    server_id = options.get(54, b"")
    host_name = options.get(12, b"")
    vendor_class = options.get(60, b"")
    return {
        "op": fields[0],
        "htype": fields[1],
        "hlen": fields[2],
        "xid": fields[4],
        "flags": fields[6],
        "ciaddr": socket.inet_ntoa(fields[7]),
        "chaddr": _mac_bytes_to_string(fields[11], fields[2]),
        "message_type": message_type[0] if message_type else None,
        "requested_ip": socket.inet_ntoa(requested_ip) if len(requested_ip) == 4 else None,
        "server_identifier": socket.inet_ntoa(server_id) if len(server_id) == 4 else None,
        "host_name": host_name.decode("ascii", errors="replace") if host_name else "",
        "vendor_class": vendor_class.decode("ascii", errors="replace") if vendor_class else "",
    }


def dhcp_message_label(message_type: int | None) -> str:
    if message_type is None:
        return "unknown"
    return _DHCP_MESSAGE_LABELS.get(message_type, f"type-{message_type}")


def build_dhcp_reply(
    request: bytes,
    *,
    message_type: int,
    offer_ip: str,
    server_ip: str,
    subnet_mask: str = "",
    router_ip: str = "",
    dns_server: str = "",
    lease_seconds: int = 300,
) -> bytes:
    if len(request) < 240:
        return b""
    header = bytearray(request[:236])
    header[0] = 2
    header[16:20] = socket.inet_aton(offer_ip)
    header[20:24] = socket.inet_aton(server_ip)
    header[24:28] = b"\x00\x00\x00\x00"
    options = bytearray(_DHCP_MAGIC_COOKIE)
    options.extend([53, 1, message_type])
    options.extend([54, 4])
    options.extend(socket.inet_aton(server_ip))
    options.extend([51, 4])
    options.extend(struct.pack("!I", lease_seconds))
    if subnet_mask:
        options.extend([1, 4])
        options.extend(socket.inet_aton(subnet_mask))
    if router_ip:
        options.extend([3, 4])
        options.extend(socket.inet_aton(router_ip))
    if dns_server:
        options.extend([6, 4])
        options.extend(socket.inet_aton(dns_server))
    options.append(255)
    return bytes(header) + bytes(options)


async def observe_dns_queries(
    *,
    expected_device_ip: str | None,
    timeout_seconds: int | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or settings.PROTOCOL_OBSERVER_TIMEOUT_SECONDS
    bind_port = port or settings.PROTOCOL_OBSERVER_DNS_PORT
    async with _observer_lock("dns"):
        sock = _bind_udp_socket(bind_port)
        response_ip = _local_ip_for_target(expected_device_ip) or "127.0.0.1"
        events: list[dict[str, Any]] = []
        loop = asyncio.get_running_loop()
        try:
            while True:
                try:
                    packet, addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 2048), timeout)
                except asyncio.TimeoutError:
                    break
                except ConnectionResetError:
                    continue
                source_ip = addr[0]
                if expected_device_ip and source_ip != expected_device_ip:
                    continue
                parsed = parse_dns_query(packet)
                if parsed is None:
                    continue
                event = {
                    "source_ip": source_ip,
                    "query_name": parsed["name"],
                    "query_type": parsed["qtype"],
                    "observer_ip": response_ip,
                }
                events.append(event)
                response = build_dns_response(packet, response_ip)
                if response:
                    await loop.sock_sendto(sock, response, addr)
        finally:
            sock.close()
        return {
            "observed": bool(events),
            "request_count": len(events),
            "events": events,
            "observer_ip": response_ip,
        }


async def observe_ntp_queries(
    *,
    expected_device_ip: str | None,
    timeout_seconds: int | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or settings.PROTOCOL_OBSERVER_TIMEOUT_SECONDS
    bind_port = port or settings.PROTOCOL_OBSERVER_NTP_PORT
    async with _observer_lock("ntp"):
        sock = _bind_udp_socket(bind_port)
        loop = asyncio.get_running_loop()
        events: list[dict[str, Any]] = []
        try:
            while True:
                try:
                    packet, addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 2048), timeout)
                except asyncio.TimeoutError:
                    break
                except ConnectionResetError:
                    continue
                source_ip = addr[0]
                if expected_device_ip and source_ip != expected_device_ip:
                    continue
                parsed = parse_ntp_request(packet)
                if parsed is None:
                    continue
                events.append(
                    {
                        "source_ip": source_ip,
                        "version": parsed["version"],
                        "mode": parsed["mode"],
                    }
                )
                response = build_ntp_response(packet)
                await loop.sock_sendto(sock, response, addr)
        finally:
            sock.close()
        version = next((event["version"] for event in events if event["mode"] == 3), None)
        return {
            "observed": bool(events),
            "request_count": len(events),
            "events": events,
            "version": version,
        }


async def observe_dhcp_activity(
    *,
    expected_mac: str | None,
    timeout_seconds: int | None = None,
    port: int | None = None,
) -> dict[str, Any]:
    timeout = timeout_seconds or settings.PROTOCOL_OBSERVER_TIMEOUT_SECONDS
    bind_port = port or settings.PROTOCOL_OBSERVER_DHCP_PORT
    async with _observer_lock("dhcp"):
        sock = _bind_udp_socket(bind_port)
        loop = asyncio.get_running_loop()
        events: list[dict[str, Any]] = []
        offer_ip = settings.PROTOCOL_OBSERVER_DHCP_OFFER_IP or ""
        server_ip = settings.PROTOCOL_OBSERVER_DHCP_ROUTER_IP or _local_ip_for_target("8.8.8.8") or ""
        observer_reply_types: list[int] = []
        lease_acknowledged = False
        try:
            while True:
                try:
                    packet, addr = await asyncio.wait_for(loop.sock_recvfrom(sock, 4096), timeout)
                except asyncio.TimeoutError:
                    break
                except ConnectionResetError:
                    continue
                parsed = parse_dhcp_packet(packet)
                if parsed is None:
                    continue
                if expected_mac and parsed["chaddr"] != expected_mac.upper():
                    continue
                event = dict(parsed)
                if offer_ip and server_ip and parsed["message_type"] in {1, 3}:
                    reply_type = 2 if parsed["message_type"] == 1 else 5
                    reply = build_dhcp_reply(
                        packet,
                        message_type=reply_type,
                        offer_ip=offer_ip,
                        server_ip=server_ip,
                        subnet_mask=settings.PROTOCOL_OBSERVER_DHCP_SUBNET_MASK,
                        router_ip=settings.PROTOCOL_OBSERVER_DHCP_ROUTER_IP,
                        dns_server=settings.PROTOCOL_OBSERVER_DHCP_DNS_SERVER,
                        lease_seconds=settings.PROTOCOL_OBSERVER_DHCP_LEASE_SECONDS,
                    )
                    if reply:
                        try:
                            await loop.sock_sendto(sock, reply, ("255.255.255.255", 68))
                            observer_reply_types.append(reply_type)
                            event["observer_reply_type"] = reply_type
                            event["observer_reply_label"] = dhcp_message_label(reply_type)
                            if reply_type == 5:
                                lease_acknowledged = True
                        except OSError as exc:
                            logger.debug("DHCP observer reply failed on port %s: %s", bind_port, exc)
                events.append(event)
        finally:
            sock.close()
        return {
            "observed": bool(events),
            "request_count": len(events),
            "events": events,
            "offer_capable": bool(offer_ip and server_ip),
            "lease_acknowledged": lease_acknowledged,
            "offered_ip": offer_ip or None,
            "server_identifier": server_ip or None,
            "observer_reply_types": observer_reply_types,
        }
