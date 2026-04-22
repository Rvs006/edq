import asyncio
import socket
import struct

import pytest

import app.services.protocol_observer as protocol_observer_module
from app.services.protocol_observer import (
    build_dhcp_reply,
    observe_dhcp_activity,
    observe_dns_queries,
    observe_ntp_queries,
    parse_dhcp_packet,
)
from app.config import settings


def _dns_query(name: str) -> bytes:
    labels = b"".join(bytes([len(part)]) + part.encode("ascii") for part in name.split("."))
    question = labels + b"\x00" + struct.pack("!HH", 1, 1)
    return struct.pack("!HHHHHH", 0x1234, 0x0100, 1, 0, 0, 0) + question


def _dhcp_packet(message_type: int, mac: bytes | None = None) -> bytes:
    client_mac = mac or bytes.fromhex("AABBCCDDEEFF")
    request = bytearray(240)
    struct.pack_into("!BBBBIHH", request, 0, 1, 1, 6, 0, 0x01020304, 0, 0x8000)
    request[28:34] = client_mac
    request[236:240] = b"\x63\x82\x53\x63"
    request.extend([53, 1, message_type, 12, 6])
    request.extend(b"edqcam")
    request.append(255)
    return bytes(request)


@pytest.mark.asyncio
async def test_observe_dns_queries_captures_local_request(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_BIND_HOST", "127.0.0.1")

    task = asyncio.create_task(
        observe_dns_queries(expected_device_ip="127.0.0.1", timeout_seconds=1, port=15353)
    )
    await asyncio.sleep(0.1)

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(_dns_query("device.local"), ("127.0.0.1", 15353))
    finally:
        sock.close()

    observed = await task

    assert observed["observed"] is True
    assert observed["events"][0]["query_name"] == "device.local"
    assert observed["events"][0]["observer_ip"]


@pytest.mark.asyncio
async def test_observe_ntp_queries_captures_local_request(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_BIND_HOST", "127.0.0.1")

    task = asyncio.create_task(
        observe_ntp_queries(expected_device_ip="127.0.0.1", timeout_seconds=1, port=10123)
    )
    await asyncio.sleep(0.1)

    packet = bytearray(48)
    packet[0] = (4 << 3) | 3
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.sendto(bytes(packet), ("127.0.0.1", 10123))
    finally:
        sock.close()

    observed = await task

    assert observed["observed"] is True
    assert observed["version"] == 4
    assert observed["events"][0]["mode"] == 3


def test_parse_dhcp_packet_and_build_reply():
    mac = bytes.fromhex("AABBCCDDEEFF")
    request = bytearray(240)
    struct.pack_into("!BBBBIHH", request, 0, 1, 1, 6, 0, 0x01020304, 0, 0x8000)
    request[28:34] = mac
    request[236:240] = b"\x63\x82\x53\x63"
    request.extend([53, 1, 1, 12, 6])
    request.extend(b"edqcam")
    request.append(255)

    parsed = parse_dhcp_packet(bytes(request))
    reply = build_dhcp_reply(
        bytes(request),
        message_type=2,
        offer_ip="192.168.4.68",
        server_ip="192.168.4.1",
        subnet_mask="255.255.255.0",
        router_ip="192.168.4.1",
        dns_server="192.168.4.1",
        lease_seconds=300,
    )

    assert parsed is not None
    assert parsed["chaddr"] == "AA:BB:CC:DD:EE:FF"
    assert parsed["message_type"] == 1
    assert socket.inet_ntoa(reply[16:20]) == "192.168.4.68"


@pytest.mark.asyncio
async def test_observe_dhcp_activity_marks_ack_when_request_is_answered(monkeypatch: pytest.MonkeyPatch):
    class FakeSocket:
        def close(self) -> None:
            return None

    class FakeLoop:
        def __init__(self) -> None:
            self.sent: list[tuple[bytes, tuple[str, int]]] = []
            self._responses = [
                (_dhcp_packet(3), ("192.168.4.68", 68)),
                asyncio.TimeoutError(),
            ]

        async def sock_recvfrom(self, sock, size):
            response = self._responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response

        async def sock_sendto(self, sock, data, addr):
            self.sent.append((data, addr))

    fake_loop = FakeLoop()
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_OFFER_IP", "192.168.4.68")
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_ROUTER_IP", "192.168.4.1")
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_SUBNET_MASK", "255.255.255.0")
    monkeypatch.setattr(settings, "PROTOCOL_OBSERVER_DHCP_DNS_SERVER", "192.168.4.1")
    monkeypatch.setattr(protocol_observer_module, "_bind_udp_socket", lambda port: FakeSocket())
    monkeypatch.setattr(protocol_observer_module.asyncio, "get_running_loop", lambda: fake_loop)

    observed = await observe_dhcp_activity(
        expected_mac="AA:BB:CC:DD:EE:FF",
        timeout_seconds=1,
        port=1067,
    )

    assert observed["observed"] is True
    assert observed["lease_acknowledged"] is True
    assert observed["offered_ip"] == "192.168.4.68"
    assert observed["server_identifier"] == "192.168.4.1"
    assert observed["observer_reply_types"] == [5]
    assert observed["events"][0]["observer_reply_type"] == 5
    assert observed["events"][0]["observer_reply_label"] == "ack"
    assert fake_loop.sent[0][1] == ("255.255.255.255", 68)
