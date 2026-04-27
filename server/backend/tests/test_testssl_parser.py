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


def test_hsts_not_offered_is_not_treated_as_present():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "hsts", "finding": "HSTS not offered", "severity": "WARN"},
    ]))

    assert parsed["hsts"] is False


def test_anonymous_cipher_keyword_is_detected_case_insensitively():
    parsed = testssl_parser.parse(_encoded_findings([
        {"id": "cipher_x", "finding": "TLS_DH_anon_WITH_AES_128_CBC_SHA", "severity": "OK"},
    ]))

    assert parsed["weak_ciphers"]
