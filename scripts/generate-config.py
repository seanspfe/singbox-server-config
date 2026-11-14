#!/usr/bin/env python3
"""Generate a sing-box server config from the template.

Every secret is produced with the exact byte/character length the protocol
requires, so the rendered config is directly usable.

Usage:
    python3 scripts/generate-config.py --output /etc/sing-box/config.json \\
        --host relay.example.com --tailscale-hostname my-node

The script also writes a client-info file (mode 0600) next to the config,
holding the REALITY public key and every credential the client needs. That
keeps the deployment self-contained: nothing has to be scraped from stderr.
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
        raise SystemExit("unrendered placeholders remain: " + ", ".join(left))

    cfg = json.loads(template)
    return cfg, pub


def write_client_info(cfg, pub: str, path: Path, host: str) -> None:
    """Persist what the client needs so it never has to be scraped from
    stderr or re-derived later. Contains secrets: written mode 0600."""
    lines = [
        "sing-box client information",
        "=" * 60,
        "",
        "REALITY public key (deliberately not stored in config.json):",
        "  " + pub,
        "",
        "Host to dial: " + (host or "<pass --host, or use this server public IP>"),
        "",
    ]

    for ib in cfg.get("inbounds", []):
        kind = ib.get("type")
        lines.append(kind + " inbound, port " + str(ib.get("listen_port")))
        for user in ib.get("users", []):
            if "uuid" in user:
                lines.append("  uuid  : " + user["uuid"])
            if "password" in user:
                lines.append("  pass  : " + user["password"])
            if user.get("flow"):
                lines.append("  flow  : " + user["flow"])
        if "password" in ib:
            lines.append("  pass  : " + ib["password"])
            lines.append("  method: " + ib["method"])
        tls = ib.get("tls") or {}
        reality = tls.get("reality") or {}
        if tls.get("enabled"):
            names = tls.get("server_name") or ",".join(reality.get("serverNames") or [])
            if names:
                lines.append("  sni   : " + names)
        if reality.get("enabled"):
            lines.append("  pbk   : " + pub)
            for sid in reality.get("short_id", []):
                lines.append("  sid   : " + sid)
            lines.append("  fp    : chrome")
        lines.append("")

    lines += [
        "Generate share links and QR codes:",
        "  python3 scripts/export-subscription.py "
        "--config <config.json> --host <domain> "
        "--public-key " + pub + " --out-dir ./sub",
        "",
    ]

    path.write_text(chr(10).join(lines), encoding="utf-8")
    os.chmod(path, 0o600)


def main() -> int:
    p = argparse.ArgumentParser(description="Generate sing-box server config")
    p.add_argument("--output", "-o", required=True, help="path to write config.json")
    p.add_argument("--host", default="",
                   help="domain or public IP clients dial; recorded in client-info")
    p.add_argument("--client-info", default="",
                   help="path for client credentials (default: <output>.client.txt)")
    p.add_argument("--tailscale-hostname", default="singbox-node",
                   help="Tailscale hostname for the embedded endpoint")
    p.add_argument("--tailscale-key", default="",
                   help="Tailscale auth key (empty means do not join a tailnet)")
    p.add_argument("--vless-uuid", default="")
    p.add_argument("--reality-private-key", default="")
    p.add_argument("--reality-short-id", default="")
    p.add_argument("--hy2-password", default="")
    p.add_argument("--trojan-password", default="")
    p.add_argument("--ss2022-password", default="")
    p.add_argument("--api-secret", default="")
    args = p.parse_args()

    cfg, pub = build(args)
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(cfg, indent=2, ensure_ascii=False) + chr(10), encoding="utf-8")
    os.chmod(out, 0o600)

    info = Path(args.client_info) if args.client_info else out.with_suffix(".client.txt")
    write_client_info(cfg, pub, info, args.host)

    print("wrote " + str(out), file=sys.stderr)
    print("wrote " + str(info) + " (client credentials, mode 0600)", file=sys.stderr)
    print("", file=sys.stderr)
    print("REALITY public key: " + pub, file=sys.stderr)
    print("it is also in " + str(info), file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

