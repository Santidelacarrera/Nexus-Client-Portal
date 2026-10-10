"""Generate persistent key material once:  python -m app.tools.genkeys --dir /keys   (idempotent)."""
from __future__ import annotations

import argparse
import base64
import os
from pathlib import Path

from app.core.keys import generate_rsa_pem


def _write(path: Path, data: str) -> None:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(data)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    d = Path(ap.parse_args().dir)
    d.mkdir(parents=True, exist_ok=True)
    made = []
    if not (d / "jwt_private.pem").exists():
        priv, pub = generate_rsa_pem(3072)
        _write(d / "jwt_private.pem", priv)
        _write(d / "jwt_public.pem", pub)
        made.append("jwt")
    if not (d / "report_signing.pem").exists():
        priv, _ = generate_rsa_pem(3072)
        _write(d / "report_signing.pem", priv)
        made.append("report-signing")
    for name in ("data.key", "webhook.secret"):
        if not (d / name).exists():
            _write(d / name, base64.b64encode(os.urandom(32)).decode())
            made.append(name)
    print(f"genkeys: created {made}" if made else "genkeys: keys already present")


if __name__ == "__main__":
    main()
