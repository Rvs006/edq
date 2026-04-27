"""Device Fingerprinter — classifies devices from scan data and determines test skips.

Runs after discovery tests (U01/U02/U08) complete. Matches against saved
DeviceProfiles or falls back to heuristic rules based on open ports, services,
and OUI vendor strings.
"""

import logging
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.device import Device, DeviceCategory
from app.models.device_profile import DeviceProfile

logger = logging.getLogger("edq.fingerprinter")


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------

@dataclass
class FingerprintResult:
    category: str = "unknown"
    vendor: str = ""
    matched_profile_id: str | None = None
    matched_profile_name: str | None = None
    skip_test_ids: list[str] = field(default_factory=list)
    skip_reasons: dict[str, str] = field(default_factory=dict)
    confidence: str = "low"  # high / medium / low
    reason: str = ""


# ---------------------------------------------------------------------------
# Heuristic classification rules
# ---------------------------------------------------------------------------

HEURISTIC_RULES: list[dict[str, Any]] = [
    # --- BAS / Building Controllers ---
    {
        "category": "controller",
        "match_any_port": [47808],  # BACnet — strongest signal
        "confidence": "high",
    },
    {
        "category": "controller",
        "match_any_vendor": [
            "easyio", "tridium", "niagara", "honeywell", "johnson controls",
            "schneider", "siemens", "distech", "reliable controls",
            "trane", "carrier", "daikin", "belimo", "sauter",
            "loytec", "wago", "beckhoff", "delta controls",
        ],
        "confidence": "high",
    },
    # --- IP Cameras ---
    {
        "category": "camera",
        "match_any_port": [554],  # RTSP
        "match_any_service": ["rtsp"],
        "confidence": "high",
    },
    {
        "category": "camera",
        "match_any_vendor": [
            "axis", "hikvision", "dahua", "pelco", "hanwha", "samsung techwin",
            "bosch", "vivotek", "mobotix", "uniview", "acti", "arecont",
            "flir", "milestone", "geovision", "reolink", "amcrest",
        ],
        "confidence": "high",
    },
    # --- Intercoms / VoIP ---
    {
        "category": "intercom",
        "match_any_port": [5060, 5061],  # SIP / SIPS
        "match_any_vendor": [
            "2n", "aiphone", "comelit", "doorbird", "grandstream",
            "zenitel", "commend", "baudisch", "mobotix",
        ],
        "confidence": "high",
    },
    # --- Access Control ---
    {
        "category": "access_panel",
        "match_any_vendor": [
            "hid", "gallagher", "lenel", "genetec", "paxton",
            "inner range", "assa abloy", "dormakaba", "salto",
            "suprema", "zkteco", "brivo", "keri",
        ],
        "confidence": "high",
    },
    # --- Lighting ---
    {
        "category": "lighting",
        "match_any_vendor": [
            "lutron", "philips lighting", "signify", "dali",
            "crestron", "control4", "helvar",
        ],
        "confidence": "medium",
    },
    # --- HVAC ---
    {
        "category": "hvac",
        "match_any_vendor": [
            "trane", "daikin", "carrier", "mitsubishi electric",
            "lg electronics", "fujitsu",
        ],
        "match_any_port": [502],  # Modbus
        "confidence": "medium",
    },
    # --- Meters ---
    {
        "category": "meter",
        "match_any_vendor": [
            "schneider electric", "accuenergy", "continental control",
            "obvius", "leviton",
        ],
        "match_any_port": [502],  # Modbus
        "confidence": "medium",
    },
    # --- IoT Sensors ---
    {
        "category": "iot_sensor",
        "match_any_port": [1883, 8883],  # MQTT / MQTTS
        "confidence": "medium",
    },
    # --- Fallback: anything with a web UI ---
    {
        "category": "unknown",
        "match_any_port": [80, 443],
        "confidence": "low",
    },
]


# ---------------------------------------------------------------------------
# Main fingerprinter class
# ---------------------------------------------------------------------------

class DeviceFingerprinter:
    """Classifies a device from U02 + U08 scan data."""

    async def fingerprint(
        self,
        db: AsyncSession,
        device_id: str,
        u08_data: dict[str, Any],
        u02_data: dict[str, Any],
        *,
        allow_port_skips: bool = True,
    ) -> FingerprintResult:
        """Run fingerprinting and return which tests to skip.

        Parameters
        ----------
        db : AsyncSession
        device_id : str – the Device row to update
        u08_data : dict – parsed output of U08 (service version detection)
        u02_data : dict – parsed output of U02 (MAC/vendor lookup)
        """
        open_ports = self._extract_ports(u08_data)
        services = self._extract_services(u08_data)
        vendor = (u02_data.get("oui_vendor") or "").strip()

        # 1. Try matching against saved DeviceProfiles
        result = await self._match_profile(db, open_ports, services, vendor)

        # 2. Fallback to heuristic rules
        if result is None:
            result = self._heuristic_classify(open_ports, services, vendor)

        # 3. Compute which tests to skip based on detected ports.
        # If the scan feeding the fingerprinter failed, absence of ports is
        # unknown, not proof that the device lacks HTTP/SSH/TLS.
        port_skip_reasons = (
            self._compute_port_skips(open_ports, services)
            if allow_port_skips
            else {}
        )
        # Merge profile-level skips (no specific reason) with port-based skips
        for tid in result.skip_test_ids:
            if tid not in port_skip_reasons:
                port_skip_reasons[tid] = "Skipped — not applicable for this device profile."
        result.skip_reasons = port_skip_reasons
        all_skips = list(set(result.skip_test_ids) | set(port_skip_reasons.keys()))
        result.skip_test_ids = sorted(all_skips, key=lambda x: (x[0], int(x[1:])))

        # 4. Update Device record
        await self._update_device(db, device_id, result, vendor, open_ports)

        logger.info(
            "Fingerprinted device %s → %s (confidence=%s, skips=%d, profile=%s)",
            device_id,
            result.category,
            result.confidence,
            len(result.skip_test_ids),
            result.matched_profile_name or "heuristic",
        )

        return result

    # ------------------------------------------------------------------
    # Profile matching
    # ------------------------------------------------------------------

    async def _match_profile(
        self,
        db: AsyncSession,
        open_ports: set[int],
        services: dict[int, str],
        vendor: str,
    ) -> FingerprintResult | None:
        """Try to match against saved DeviceProfile entries."""
        query = select(DeviceProfile).where(DeviceProfile.is_active == True)
        rows = (await db.execute(query)).scalars().all()

        best: DeviceProfile | None = None
        best_score = 0

        vendor_lower = vendor.lower()

        for profile in rows:
            rules = profile.fingerprint_rules
            if not rules:
                continue

            score = 0

            # Port signature matching. Support both "required_ports" +
            # "optional_ports" and "port_hints" (the key name used by
            # init_db.py seeded profiles). port_hints are treated as a
            # weaker signal (any match counts, 1 point each).
            required_ports = set(rules.get("required_ports", []))
            if required_ports and required_ports.issubset(open_ports):
                score += len(required_ports) * 2

            optional_ports = set(rules.get("optional_ports", []))
            if optional_ports:
                score += len(optional_ports & open_ports)

            port_hints = set(rules.get("port_hints", []))
            if port_hints:
                score += len(port_hints & open_ports)

            # Vendor matching. Support both "vendors" and "oui_vendors"
            # (seeded key). oui_vendors are matched the same way.
            vendor_patterns = [v.lower() for v in rules.get("vendors", [])]
            vendor_patterns += [v.lower() for v in rules.get("oui_vendors", [])]
            if vendor_patterns and any(v in vendor_lower for v in vendor_patterns):
                score += 5

            # Service matching. Support both "services" and "service_hints".
            service_patterns = [s.lower() for s in rules.get("services", [])]
            service_patterns += [s.lower() for s in rules.get("service_hints", [])]
            if service_patterns:
                svc_values = {s.lower() for s in services.values()}
                if any(sp in sv for sp in service_patterns for sv in svc_values):
                    score += 3

            if score > best_score:
                best_score = score
                best = profile

        if best is None or best_score < 2:
            return None

        # Determine skip list from profile
        skip_ids: list[str] = []
        if best.fingerprint_rules and best.fingerprint_rules.get("skip_test_ids"):
            skip_ids = list(best.fingerprint_rules["skip_test_ids"])

        confidence = "high" if best_score >= 7 else "medium" if best_score >= 4 else "low"

        return FingerprintResult(
            category=best.category,
            vendor=vendor,
            matched_profile_id=best.id,
            matched_profile_name=best.name,
            skip_test_ids=skip_ids,
            confidence=confidence,
            reason=f"Matched profile '{best.name}' (score={best_score})",
        )

    # ------------------------------------------------------------------
    # Heuristic classification
    # ------------------------------------------------------------------

    def _heuristic_classify(
        self,
        open_ports: set[int],
        services: dict[int, str],
        vendor: str,
    ) -> FingerprintResult:
        """Classify using built-in heuristic rules."""
        vendor_lower = vendor.lower()
        svc_values = {s.lower() for s in services.values()}

        for rule in HEURISTIC_RULES:
            matched = False

            # Port match
            match_ports = set(rule.get("match_any_port", []))
            if match_ports and match_ports & open_ports:
                matched = True

            # Vendor match
            match_vendors = rule.get("match_any_vendor", [])
            if match_vendors and any(v in vendor_lower for v in match_vendors):
                matched = True

            # Service match
            match_services = rule.get("match_any_service", [])
            if match_services and any(
                ms in sv for ms in match_services for sv in svc_values
            ):
                matched = True

            # Absent-port check (e.g. switches with no HTTP)
            absent = set(rule.get("match_all_ports_absent", []))
            if absent and not (absent & open_ports):
                matched = True

            if matched:
                return FingerprintResult(
                    category=rule["category"],
                    vendor=vendor,
                    confidence=rule.get("confidence", "low"),
                    reason=f"Heuristic rule: {rule['category']}",
                )

        return FingerprintResult(
            category="unknown",
            vendor=vendor,
            confidence="low",
            reason="No heuristic rule matched",
        )

    # ------------------------------------------------------------------
    # Port-based test skips
    # ------------------------------------------------------------------

    def _compute_port_skips(self, open_ports: set[int], services: dict[int, str] | None = None) -> dict[str, str]:
        """Determine which tests to skip based on absent ports/services.

        Returns a dict mapping test_id → human-readable skip reason.
        """
        skips: dict[str, str] = {}
        services = services or {}

        def _has_service_port(*keywords: str, common_ports: set[int] | None = None) -> bool:
            common_ports = common_ports or set()
            if open_ports & common_ports:
                return True
            lowered = [svc.lower() for svc in services.values()]
            return any(any(keyword in svc for keyword in keywords) for svc in lowered)

        # No HTTPS/TLS → skip TLS tests. Check port 443 first, then any HTTPS service.
        has_https = 443 in open_ports
        if not has_https and services:
            https_keywords = {"ssl", "https", "ssl/http", "ssl/https"}
            has_https = any(
                svc.lower() in https_keywords or "https" in svc.lower() or "ssl" in svc.lower()
                for svc in services.values()
            )
        if not has_https:
            reason = "Skipped — no HTTPS/TLS service detected on this device, so TLS tests cannot run."
            for tid in ("U10", "U11", "U12", "U13"):
                skips[tid] = reason

        # No SSH service → skip SSH audit
        if not _has_service_port("ssh", common_ports={22}):
            skips["U15"] = "Skipped — no SSH service detected on this device."

        # No RTSP service → skip RTSP auth test
        if not _has_service_port("rtsp", common_ports={554, 8554}):
            skips["U37"] = "Skipped — no RTSP service detected on this device. No video stream to test."

        # No HTTP at all → skip HTTP-specific tests
        has_http = _has_service_port(
            "http",
            "www",
            common_ports={80, 443, 8000, 8008, 8080, 8081, 8443, 8888},
        )
        if not has_http:
            reason = "Skipped — no HTTP/HTTPS service detected."
            for tid in ("U14", "U16", "U17", "U18", "U35"):
                skips[tid] = reason

        return skips

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_ports(self, scan_data: dict[str, Any]) -> set[int]:
        """Extract set of open port numbers from parsed scan data."""
        ports: set[int] = set()
        for p in scan_data.get("open_ports", []):
            try:
                ports.add(int(p["port"]))
            except (KeyError, TypeError, ValueError):
                continue
        return ports

    def _extract_services(self, scan_data: dict[str, Any]) -> dict[int, str]:
        """Extract port→service mapping from parsed scan data."""
        services: dict[int, str] = {}
        for p in scan_data.get("open_ports", []):
            try:
                port = int(p["port"])
                svc = p.get("service", "") or p.get("name", "")
                if svc:
                    services[port] = svc
            except (KeyError, TypeError, ValueError):
                continue
        return services

    async def _update_device(
        self,
        db: AsyncSession,
        device_id: str,
        result: FingerprintResult,
        vendor: str,
        open_ports: set[int],
    ) -> None:
        """Update the Device row with classification results."""
        device = await db.get(Device, device_id)
        if not device:
            return

        # Map string category to DeviceCategory enum
        try:
            device.category = DeviceCategory(result.category)
        except ValueError:
            device.category = DeviceCategory.UNKNOWN

        if vendor and not device.oui_vendor:
            device.oui_vendor = vendor

        if result.matched_profile_id and not device.profile_id:
            device.profile_id = result.matched_profile_id

        # Store open ports on device for future reference
        device.open_ports = [{"port": p} for p in sorted(open_ports)]

        # Store full fingerprint in discovery_data
        device.discovery_data = {
            "fingerprint": {
                "category": result.category,
                "confidence": result.confidence,
                "matched_profile_id": result.matched_profile_id,
                "matched_profile_name": result.matched_profile_name,
                "skip_test_ids": result.skip_test_ids,
                "reason": result.reason,
            }
        }

        await db.flush()

    # ------------------------------------------------------------------
    # Auto-learn from completed run
    # ------------------------------------------------------------------

    async def learn_from_run(
        self,
        db: AsyncSession,
        device_id: str,
        run_metadata: dict[str, Any],
    ) -> DeviceProfile | None:
        """After a run completes, check if we should save a new DeviceProfile.

        Only creates a profile if no existing profile matched and the device
        has enough distinguishing characteristics.
        """
        fingerprint = run_metadata.get("fingerprint", {})

        # Already matched a profile — nothing to learn
        if fingerprint.get("matched_profile_id"):
            return None

        device = await db.get(Device, device_id)
        if not device:
            return None

        vendor = device.oui_vendor or device.manufacturer or ""
        if not vendor:
            return None  # Not enough info to create a useful profile

        category = device.category.value if device.category else "unknown"
        open_ports = [p["port"] for p in (device.open_ports or []) if "port" in p]

        if not open_ports:
            return None

        # Check if a similar profile already exists
        existing = await db.execute(
            select(DeviceProfile).where(
                DeviceProfile.manufacturer == vendor,
                DeviceProfile.category == category,
                DeviceProfile.is_active == True,
            )
        )
        if existing.scalar_one_or_none():
            return None

        # Create new auto-learned profile
        profile = DeviceProfile(
            name=f"{vendor} - {category} (auto-learned)",
            manufacturer=vendor,
            model_pattern=device.model or "*",
            category=category,
            description=f"Auto-generated profile from test run on {device.ip_address}",
            is_active=True,
            auto_generated=True,
            fingerprint_rules={
                "required_ports": open_ports[:10],  # Cap at 10 most important
                "vendors": [vendor.lower()],
                "skip_test_ids": fingerprint.get("skip_test_ids", []),
            },
        )
        db.add(profile)
        await db.flush()
        await db.refresh(profile)

        logger.info(
            "Auto-learned new profile '%s' (id=%s) from device %s",
            profile.name,
            profile.id,
            device_id,
        )

        return profile


# Module-level singleton
fingerprinter = DeviceFingerprinter()
