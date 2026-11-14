#!/usr/bin/env python3
"""Generate a sing-box server config from the template.

Every secret is produced with the exact byte/character length the protocol
requires, so the rendered config is directly usable.

Usage:
    python3 scripts/generate-config.py --output /etc/sing-box/config.json
    python3 scripts/generate-config.py --output out.json --tailscale-key tskey-xxx
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import string
import sys
import uuid as uuidlib
from pathlib import Path

TEMPLATE = Path(__file__).resolve().parent.parent / "templates" / "config.json.example"

# Shadowsocks 2022 requires a key of exactly this many raw bytes, base64 encoded.
SS2022_AES128_KEY_BYTES = 16


def b64url(raw: bytes) -> str:
    """base64url without padding: the encoding sing-box and Xray use for keys."""
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def gen_uuid() -> str:
    """36 chars, RFC 4122 v4."""
    return str(uuidlib.uuid4())


def gen_reality_keypair():
    """REALITY uses a 32-byte X25519 key: private/public are 43-char base64url."""
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives import serialization
    except ImportError:
        raise SystemExit(
            "missing dependency: pip install cryptography "
            "(or use: sing-box generate reality-keypair)"
        )
    key = X25519PrivateKey.generate()
    priv = key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub = key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PublicFormat.Raw,
    )
    return b64url(priv), b64url(pub)


def gen_short_id(nbytes: int = 4) -> str:
    """REALITY short id: 8 hex chars (4 bytes). Must be even-length hex."""
    return secrets.token_hex(nbytes)


def gen_password(nbytes: int = 16) -> str:
    """Printable password used by hysteria2 and trojan."""
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(nbytes))


def gen_ss2022_password() -> str:
    """Shadowsocks 2022: base64 of exactly 16 raw bytes for aes-128-gcm."""
    return base64.b64encode(secrets.token_bytes(SS2022_AES128_KEY_BYTES)).decode()


def gen_secret(nbytes: int = 24) -> str:
    """Generic shared secret for the api and clash_api services."""
    return secrets.token_urlsafe(nbytes)


def build(args):
    template = TEMPLATE.read_text(encoding="utf-8")

    priv, pub = gen_reality_keypair()
    api_secret = args.api_secret or gen_secret()
    values = {
        "VLESS_UUID": args.vless_uuid or gen_uuid(),
        "REALITY_PRIVATE_KEY": args.reality_private_key or priv,
        "REALITY_SHORT_ID": args.reality_short_id or gen_short_id(),
        "HY2_PASSWORD": args.hy2_password or gen_password(),
        "TROJAN_PASSWORD": args.trojan_password or gen_password(),
        "SS2022_PASSWORD": args.ss2022_password or gen_ss2022_password(),
        "TAILSCALE_HOSTNAME": args.tailscale_hostname,
        "TAILSCALE_AUTH_KEY": args.tailscale_key or "",
        "CLASH_API_SECRET": api_secret,
        "API_SECRET": api_secret,
    }

    for key, value in values.items():
        template = template.replace("%%" + key + "%%", value)

    left = [ln for ln in template.splitlines() if "%%" in ln]
    if left:
        raise SystemExit("unrendered placeholders remain:\n" + "\n".join(left))

    cfg = json.loads(template)
    cfg["_meta"] = {
        "generated_by": "scripts/generate-config.py",
        "reality_public_key": pub,
    }
    return cfg


def main() -> int:
    p = argparse.ArgumentParser(description="Generate sing-box server config")
    p.add_argument("--output", "-o", required=True, help="path to write config.json")
    p.add_argument("--tailscale-hostname", default="singbox-node",
                   help="Tailscale hostname for the embedded endpoint")
    p.add_argument("--tailscale-key", default="",
                   help="Tailscale auth key (leave empty to log in later)")
    p.add_argument("--vless-uuid", default="")
    p.add_argument("--reality-private-key", default="")
    p.add_argument("--reality-short-id", default="")
    p.add_argument("--hy2-password", default="")
    p.add_argument("--trojan-password", default="")
    p.add_argument("--ss2022-password", default="")
    p.add_argument("--api-secret", default="")
    args = p.parse_args()

    cfg = build(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.chmod(out, 0o600)

    print("wrote " + str(out))
    print("REALITY public key: " + cfg["_meta"]["reality_public_key"])
    print("keep that public key for the client configuration")
    return 0


if __name__ == "__main__":
    sys.exit(main())

