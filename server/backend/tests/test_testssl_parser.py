"""Regression coverage for testssl.sh parser edge cases."""

import base64
import json

from app.services.parsers.testssl_parser import testssl_parser


def _encoded_findings(findings: list[dict]) -> str:
    return base64.b64encode(json.dumps(findings).encode("utf-8")).decode("ascii")


def test_tls12_and_tls13_are_not_misclassified_as_tls10():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "TLS1_2", "finding": "offered", "severity": "OK"},
        {"id": "TLS1_3", "finding": "offered", "severity": "OK"},
    ]))

    assert parsed["tls_versions"] == ["TLSv1.2", "TLSv1.3"]
    assert parsed["weak_versions"] == []


def test_disabled_protocols_are_not_treated_as_offered():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "SSLv2", "finding": "not offered (OK)", "severity": "OK"},
        {"id": "SSLv3", "finding": "not offered (OK)", "severity": "OK"},
        {"id": "TLS1_0", "finding": "offered", "severity": "WARN"},
    ]))

    assert parsed["tls_versions"] == ["TLSv1.0"]
    assert parsed["weak_versions"] == ["TLSv1.0"]


def test_hsts_not_offered_is_not_treated_as_present():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "hsts", "finding": "HSTS not offered", "severity": "WARN"},
    ]))

    assert parsed["hsts"] is False


def test_self_signed_certificate_is_not_treated_as_valid():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "cert_chain_of_trust", "finding": "self-signed certificate in certificate chain", "severity": "WARN"},
        {"id": "cert_subject", "finding": "CN=device.local", "severity": "INFO"},
        {"id": "cert_issuer", "finding": "CN=device.local", "severity": "INFO"},
    ]))

    assert parsed["cert_valid"] is False
    assert parsed["cert_has_issue"] is True
    assert parsed["cert_self_signed"] is True
    assert parsed["cert_trust_verified"] is False


def test_untrusted_certificate_chain_marks_trust_unverified():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "cert_chain_of_trust", "finding": "unable to verify the first certificate", "severity": "WARN"},
        {"id": "cert_subject", "finding": "CN=device.local", "severity": "INFO"},
        {"id": "cert_issuer", "finding": "CN=Private Device CA", "severity": "INFO"},
    ]))

    assert parsed["cert_valid"] is False
    assert parsed["cert_has_issue"] is True
    assert parsed["cert_trust_verified"] is False


def test_anonymous_cipher_keyword_is_detected_case_insensitively():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "cipher_x", "finding": "TLS_DH_anon_WITH_AES_128_CBC_SHA", "severity": "OK"},
    ]))

    assert parsed["weak_ciphers"]


def test_cipher_ids_containing_tls_version_are_parsed_as_ciphers():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "TLS1_2", "finding": "offered", "severity": "OK"},
        {"id": "cipher_tls12_aes256", "finding": "ECDHE-ECDSA-AES256-GCM-SHA384", "severity": "OK"},
    ]))

    assert parsed["tls_versions"] == ["TLSv1.2"]
    assert parsed["ciphers"] == [
        {
            "id": "cipher_tls12_aes256",
            "name": "ECDHE-ECDSA-AES256-GCM-SHA384",
            "severity": "OK",
        }
    ]


def test_cipher_summary_entries_are_not_counted_as_suites():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "pre_128cipher", "finding": "No 128 cipher limit bug", "severity": "INFO"},
        {
            "id": "supportedciphers_TLSv1_2",
            "finding": "ECDHE-RSA-AES256-GCM-SHA384 TLS_AES_128_GCM_SHA256",
            "severity": "INFO",
        },
        {
            "id": "cipher-tls1_3_x1301",
            "finding": (
                "TLSv1.3   x1301   TLS_AES_128_GCM_SHA256            "
                "ECDH 253   AESGCM      128      TLS_AES_128_GCM_SHA256"
            ),
            "severity": "OK",
        },
    ]))

    assert parsed["ciphers"] == [
        {
            "id": "cipher-tls1_3_x1301",
            "name": "TLS_AES_128_GCM_SHA256",
            "openssl_name": "TLS_AES_128_GCM_SHA256",
            "protocol": "TLSv1.3",
            "hexcode": "x1301",
            "key_exchange": "ECDH 253",
            "encryption": "AESGCM",
            "bits": 128,
            "iana_name": "TLS_AES_128_GCM_SHA256",
            "severity": "OK",
        }
    ]
    assert parsed["weak_ciphers"] == []


def test_low_severity_cipher_is_reported_as_weak():
    parsed = testssl_parser.parse(_encoded_findings([
        {
            "id": "cipher-tls1_2_xc013",
            "finding": (
                "TLSv1.2   xc013   ECDHE-RSA-AES128-SHA              "
                "ECDH 256   AES         128      TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA"
            ),
            "severity": "LOW",
        },
    ]))

    assert parsed["ciphers"][0]["name"] == "TLS_ECDHE_RSA_WITH_AES_128_CBC_SHA"
    assert parsed["weak_ciphers"] == parsed["ciphers"]


def test_stdout_cipher_table_is_parsed_as_cipher_inventory():
    stdout = """
TLSv1
 xc014   ECDHE-RSA-AES256-SHA              ECDH 256   AES         256      TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA
TLSv1.3
 x1301   TLS_AES_128_GCM_SHA256            ECDH 253   AESGCM      128      TLS_AES_128_GCM_SHA256
"""

    parsed = testssl_parser.parse_from_stdout(stdout)

    assert [cipher["name"] for cipher in parsed["ciphers"]] == [
        "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
        "TLS_AES_128_GCM_SHA256",
    ]
    assert parsed["tls_versions"] == ["TLSv1", "TLSv1.3"]
    assert parsed["weak_versions"] == ["TLSv1.0"]
    assert [cipher["name"] for cipher in parsed["weak_ciphers"]] == [
        "TLS_ECDHE_RSA_WITH_AES_256_CBC_SHA",
    ]
