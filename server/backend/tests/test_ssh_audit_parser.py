from app.services.parsers.ssh_audit_parser import ssh_audit_parser


def test_text_parser_flags_bracketed_fail_host_key_algorithms():
    parsed = ssh_audit_parser.parse(
        {
            "stdout": "\n".join(
                [
                    "SSH-2.0-Dropbear",
                    "# host-key algorithms",
                    "ecdsa-sha2-nistp521 -- [fail] using elliptic curves that are suspected as being backdoored",
                    "ecdsa-sha2-nistp384 -- [fail] using elliptic curves that are suspected as being backdoored",
                    "ssh-rsa -- [warn] using SHA-1",
                ]
            )
        }
    )

    assert parsed["overall_score"] == "warning"
    assert parsed["weak_host_keys"] == ["ssh-rsa"]
