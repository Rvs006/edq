from app.services.evaluation import evaluate_result


def test_u04_dhcp_offer_is_reported_as_segment_evidence_not_device_proof():
    verdict, comment = evaluate_result(
        "U04",
        {
            "dhcp_detected": True,
            "dhcp_server": "192.168.4.1",
            "offered_ip": "192.168.4.68",
            "script_output": "IP Offered: 192.168.4.68",
        },
    )

    assert verdict == "info"
    assert "DHCP offer observed" in comment
    assert "does not prove the device under test accepted the lease" in comment
    assert "IP Offered: 192.168.4.68" in comment


def test_u04_passes_when_edq_acknowledges_dhcp_lease():
    verdict, comment = evaluate_result(
        "U04",
        {
            "dhcp_observed": True,
            "dhcp_lease_acknowledged": True,
            "offered_ip": "192.168.4.68",
            "dhcp_server": "192.168.4.1",
            "dhcp_events": [{"message_type": 1}, {"message_type": 3}],
        },
    )

    assert verdict == "pass"
    assert "lease acknowledgement" in comment
    assert "192.168.4.68" in comment


def test_u04_observation_only_calls_out_missing_offer_configuration():
    verdict, comment = evaluate_result(
        "U04",
        {
            "dhcp_observed": True,
            "dhcp_lease_acknowledged": False,
            "offer_capable": False,
            "dhcp_events": [{"message_type": 1}, {"message_type": 3}],
        },
    )

    assert verdict == "info"
    assert "Observed client messages: discover, request." in comment
    assert "observation-only" in comment
    assert "Protocol Harness DHCP offer settings" in comment


def test_u09_uses_protocol_and_service_labels_in_non_whitelist_findings():
    verdict, comment = evaluate_result(
        "U09",
        {
            "open_ports": [
                {"port": 21, "protocol": "tcp", "service": "ftp"},
                {"port": 445, "protocol": "tcp", "service": "microsoft-ds"},
            ]
        },
        whitelist_entries=[],
    )

    assert verdict == "fail"
    assert "TCP port 21: FTP found open, disable." in comment
    assert "TCP port 445: SAMBA found open, disable if not required." in comment


def test_u26_requires_observed_sync_for_pass():
    verdict, comment = evaluate_result(
        "U26",
        {
            "ntp_open": True,
            "ntp_service": "ntp",
            "ntp_version": "4",
            "ntp_script_output": "ntp-info: version 4",
            "ntp_observed_sync": False,
        },
    )

    assert verdict == "info"
    assert "UDP/123 responded" in comment
    assert "synchronisation is still unproven" in comment
    assert "version 4" in comment.lower()


def test_u29_requires_observed_dns_requests_for_pass():
    verdict, comment = evaluate_result(
        "U29",
        {
            "dns_open": True,
            "dns_service": "domain",
            "dns_version": "dnsmasq 2.89",
            "dns_observed_requests": False,
        },
    )

    assert verdict == "info"
    assert "DNS-related service detected on port 53." in comment
    assert "request-direction verification is still required" in comment


def test_u36_includes_script_output_in_banner_comment():
    verdict, comment = evaluate_result(
        "U36",
        {
            "open_ports": [
                {
                    "port": 80,
                    "protocol": "tcp",
                    "state": "open",
                    "service": "http",
                    "version": "nginx 1.16.1",
                    "scripts": [{"id": "banner", "output": "Server: nginx/1.16.1", "details": {}}],
                }
            ]
        },
    )

    assert verdict == "info"
    assert "PORT\tSTATE\tSERVICE\tVERSION" in comment
    assert "Server: nginx/1.16.1" in comment
