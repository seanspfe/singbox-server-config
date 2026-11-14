#!/usr/bin/env python3
"""Export share links and QR codes for every inbound in a sing-box config.

Produces standard share URIs that Shadowrocket, Happ, sing-box, Clash Meta and
v2rayNG all understand, plus a base64 subscription file and one QR code per
node for scanning.

Usage:
    python3 scripts/export-subscription.py \
        --config /etc/sing-box/config.json \
        --host relay.example.com \
        --public-key <REALITY_PUBLIC_KEY> \
        --out-dir ./out

--host is what the client dials: a domain (recommended, and required for the
certificate-backed inbounds) or a bare public IP.

The Tailscale endpoint is not exported: it joins a tailnet, it is not a
client node.
"""
from __future__ import annotations

import argparse
import base64
import json
import sys
from pathlib import Path
from urllib.parse import quote

# Name shown in the client's node list.
LABELS = {
    "vless": "VLESS-REALITY",
    "hysteria2": "Hysteria2",
    "trojan": "Trojan",
    "shadowsocks": "SS2022",
}


def b64(data: str) -> str:
    return base64.urlsafe_b64encode(data.encode()).decode().rstrip("=")


def vless_link(ib: dict, host: str, public_key: str) -> str:
    user = ib["users"][0]
    reality = ib["tls"]["reality"]
    params = {
        "type": "tcp",
        "security": "reality",
        "sni": ib["tls"]["server_name"],
        "pbk": public_key,
        "sid": reality["short_id"][0],
        "fp": "chrome",
    }
    if user.get("flow"):
        params["flow"] = user["flow"]
    query = "&".join(f"{k}={quote(str(v), safe='')}" for k, v in params.items())
    label = quote(f"{LABELS['vless']}-{host}", safe="")
    return f"vless://{user['uuid']}@{host}:{ib['listen_port']}?{query}#{label}"


def hysteria2_link(ib: dict, host: str) -> str:
    password = ib["users"][0]["password"]
    sni = host
    query = f"sni={quote(sni, safe='')}&alpn=h3"
    label = quote(f"{LABELS['hysteria2']}-{host}", safe="")
    return f"hysteria2://{quote(password, safe='')}@{host}:{ib['listen_port']}/?{query}#{label}"


def trojan_link(ib: dict, host: str) -> str:
    password = ib["users"][0]["password"]
    query = f"sni={quote(host, safe='')}&alpn=h2,http%2F1.1"
    label = quote(f"{LABELS['trojan']}-{host}", safe="")
    return f"trojan://{quote(password, safe='')}@{host}:{ib['listen_port']}?{query}#{label}"


def ss_link(ib: dict, host: str) -> str:
    password = ib["password"]
    userinfo = b64(f"{ib['method']}:{password}")
    label = quote(f"{LABELS['shadowsocks']}-{host}", safe="")
    return f"ss://{userinfo}@{host}:{ib['listen_port']}#{label}"


BUILDERS = {
    "vless": vless_link,
    "hysteria2": hysteria2_link,
    "trojan": trojan_link,
    "shadowsocks": ss_link,
}


def build_links(cfg: dict, host: str, public_key: str):
    links = []
    for ib in cfg.get("inbounds", []):
        kind = ib.get("type")
        builder = BUILDERS.get(kind)
        if not builder:
            continue
        if kind == "vless":
            links.append((kind, builder(ib, host, public_key)))
        else:
            links.append((kind, builder(ib, host)))
    return links


def write_qr(text: str, path: Path, segno) -> None:
    qr = segno.make(text, error="m")
    if path.suffix == ".png":
        # PNG scans more reliably on a phone than an SVG rendered at some
        # arbitrary zoom level.
        qr.save(str(path), scale=8, border=3)
    else:
        qr.save(str(path), scale=6, border=3)


def main() -> int:
    p = argparse.ArgumentParser(description="Export share links and QR codes")
    p.add_argument("--config", required=True, help="sing-box config.json")
    p.add_argument("--host", default="", help="domain or public IP clients dial")
    p.add_argument("--public-key", default="", help="REALITY public key")
    p.add_argument("--client-info", default="",
                   help="read host and public key from this file instead "
                        "(written by generate-config.py)")
    p.add_argument("--out-dir", default="./out", help="where to write links and QR codes")
    p.add_argument("--no-qr", action="store_true", help="skip QR generation (no segno needed)")
    args = p.parse_args()

    host, public_key = args.host, args.public_key
    if args.client_info:
        text = Path(args.client_info).read_text(encoding="utf-8")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("Host to dial:") and not host:
                value = stripped.split(":", 1)[1].strip()
                if not value.startswith("<"):
                    host = value
            if stripped.startswith("pbk") and not public_key:
                public_key = stripped.split(":", 1)[1].strip()
    if not host:
        print("--host is required (or pass --client-info)", file=sys.stderr)
        return 2
    if not public_key:
        print("--public-key is required (or pass --client-info)", file=sys.stderr)
        return 2

    cfg = json.loads(Path(args.config).read_text(encoding="utf-8"))
    links = build_links(cfg, host, public_key)
    if not links:
        print("no exportable inbounds found", file=sys.stderr)
        return 1

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)

    (out / "links.txt").write_text("\n".join(u for _, u in links) + "\n", encoding="utf-8")

    # A subscription is the same links, base64 encoded, one per line.
    sub = b64("\n".join(u for _, u in links))
    (out / "subscription.txt").write_text(sub + "\n", encoding="utf-8")

    print("wrote " + str(out / "links.txt") + " (" + str(len(links)) + " nodes)")
    for kind, uri in links:
        print("  " + kind + ": " + uri)

    if args.no_qr:
        return 0

    try:
        import segno
    except ImportError:
        print("", file=sys.stderr)
        print("segno not installed; QR codes skipped. pip install segno", file=sys.stderr)
        return 0

    for kind, uri in links:
        name = kind + ".png"
        write_qr(uri, out / name, segno)
        print("  qr: " + str(out / name))

    # One QR that contains the whole subscription, for clients that import it.
    write_qr(sub, out / "subscription.png", segno)
    print("  qr: " + str(out / "subscription.png"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

