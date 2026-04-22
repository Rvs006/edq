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


def test_u11_lists_detected_cipher_suites_in_comment():
    verdict, comment = evaluate_result(
        "U11",
        {
            "ciphers": [
                {"name": "TLS_AES_256_GCM_SHA384"},
                {"name": "TLS_CHACHA20_POLY1305_SHA256"},
            ],
            "weak_ciphers": [],
        },
    )

    assert verdict == "pass"
    assert "Detected cipher suites:" in comment
    assert "TLS_AES_256_GCM_SHA384" in comment


def test_u12_includes_subject_issuer_and_validity_window():
    verdict, comment = evaluate_result(
        "U12",
        {
            "cert_valid": True,
            "cert_subject": "CN=device.local",
            "cert_issuer": "CN=EDQ Test CA",
            "cert_not_before": "2026-04-01",
            "cert_not_after": "2027-04-01",
        },
    )

    assert verdict == "pass"
    assert "Subject: CN=device.local" in comment
    assert "Issuer: CN=EDQ Test CA" in comment
    assert "Not Before: 2026-04-01" in comment
    assert "Not After: 2027-04-01" in comment


def test_u14_reports_captured_header_dump():
    verdict, comment = evaluate_result(
        "U14",
        {
            "http_service_detected": True,
            "headers": {
                "Content-Security-Policy": "default-src 'self'",
                "X-Frame-Options": "DENY",
                "X-Content-Type-Options": "nosniff",
                "Referrer-Policy": "same-origin",
            },
            "raw_headers": "HTTP/1.1 200 OK\nContent-Security-Policy: default-src 'self'\nX-Frame-Options: DENY",
        },
    )

    assert verdict == "pass"
    assert "HTTP/1.1 200 OK" in comment
    assert "Content-Security-Policy" in comment


def test_u15_includes_algorithm_inventory_in_comment():
    verdict, comment = evaluate_result(
        "U15",
        {
            "overall_score": "good",
            "ssh_version": "SSH-2.0-OpenSSH_9.8",
            "kex_algorithms": ["curve25519-sha256"],
            "ciphers": ["chacha20-poly1305@openssh.com"],
            "macs": ["hmac-sha2-256-etm@openssh.com"],
            "host_keys": ["ssh-ed25519"],
            "weak_kex": [],
            "weak_ciphers": [],
            "weak_macs": [],
            "weak_host_keys": [],
        },
    )

    assert verdict == "pass"
    assert "Banner: SSH-2.0-OpenSSH_9.8" in comment
    assert "KEX: curve25519-sha256" in comment
    assert "Ciphers: chacha20-poly1305@openssh.com" in comment


def test_u17_reports_lockout_duration_when_present():
    verdict, comment = evaluate_result(
        "U17",
        {
            "lockout_detected": True,
            "lockout_duration_seconds": 120,
        },
    )

    assert verdict == "pass"
    assert "Lockout duration: 2 minute(s)." in comment


def test_u18_no_longer_passes_when_http_is_absent():
    verdict, comment = evaluate_result(
        "U18",
        {
            "redirects_to_https": False,
            "http_open": False,
        },
    )

    assert verdict == "advisory"
    assert "does not satisfy a redirect verification requirement" in comment


def test_u19_includes_device_type_running_guess_and_cpe():
    verdict, comment = evaluate_result(
        "U19",
        {
            "os_fingerprint": "Linux 5.X",
            "device_type": "general purpose",
            "running": ["Linux 5.X"],
            "os_cpe": ["cpe:/o:linux:linux_kernel:5"],
        },
    )

    assert verdict == "info"
    assert "Device type: general purpose." in comment
    assert "Running guesses: Linux 5.X." in comment
    assert "CPE: cpe:/o:linux:linux_kernel:5." in comment
