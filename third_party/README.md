# Third-party scanner source archives

These archives are vendored so the EDQ backend image can build on networks where
Docker cannot reach GitHub or codeload.github.com. Keep the versions aligned with
`server/backend/Dockerfile`.

| Archive | Upstream source | SHA256 |
| --- | --- | --- |
| `testssl-v3.2.3.tar.gz` | `https://github.com/drwetter/testssl.sh/archive/refs/tags/v3.2.3.tar.gz` | `1c4bb10185a67592164eb870c717b8bdd03f290c8d68f9a8c658335ff5ac8b91` |
| `hydra-v9.5.tar.gz` | `https://github.com/vanhauser-thc/thc-hydra/archive/refs/tags/v9.5.tar.gz` | `9dd193b011fdb3c52a17b0da61a38a4148ffcad731557696819d4721d1bee76b` |
| `nikto-2.6.0.tar.gz` | `https://github.com/sullo/nikto/archive/refs/tags/2.6.0.tar.gz` | `656554f9aeba8c462689582b59d141369dbcadac11141cd02752887f363430ec` |

When updating a tool:

1. Download the upstream release archive.
2. Replace the matching file in this directory.
3. Update the SHA256 build arg in `server/backend/Dockerfile`.
4. Update the table above.
5. Rebuild with `docker compose build --no-cache backend`.
