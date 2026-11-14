# sing-box server config

A production-shaped **sing-box server** configuration for a single VPS:
VLESS + REALITY + Vision, Hysteria2, Trojan, and Shadowsocks 2022, plus an
embedded Tailscale endpoint — all in one process.

The committed template contains **no real credentials**. Every secret is a
placeholder; `scripts/generate-config.py` fills them in with correctly sized
random values for you.

## What is included

| Inbound | Port | Transport / security | Notes |
|---|---|---|---|
| `vless-reality-in` | 8443 | VLESS + REALITY + `xtls-rprx-vision` | steals `www.microsoft.com`; no own certificate needed |
| `hysteria2-in` | 4443 | QUIC / h3 | needs a real certificate; masquerades as a website |
| `trojan-in` | 13159 | TLS (h2, http/1.1) | shares the same certificate |
| `ss2022-in` | 2096 | Shadowsocks 2022 `2022-blake3-aes-128-gcm` | key must decode to exactly 16 bytes |

Outbounds are `direct` + `block`; the only route rule blocks BitTorrent.
An embedded `tailscale` endpoint joins the node to your tailnet without a
separate `tailscaled`.

## Quick start

```bash
sudo apt install -y python3 python3-pip
pip install cryptography

# 1. generate a config with fresh secrets
sudo python3 scripts/generate-config.py --output /etc/sing-box/config.json \
     --tailscale-hostname my-node

# 2. it prints the REALITY public key - keep it for the client side
```

The script writes the file with mode `0600` and prints the REALITY public key,
which is the only generated value the client needs.

Full deployment steps (certificates, systemd, firewall, client config) are in
[docs/deploy.md](docs/deploy.md).

## Length requirements the script enforces

| Value | Requirement |
|---|---|
| VLESS UUID | 36 chars, RFC 4122 v4 |
| REALITY private key | 32 raw bytes, base64url without padding → 43 chars |
| REALITY short id | even-length hex, 8 chars (4 bytes) typical |
| Shadowsocks 2022 key | base64 of exactly 16 raw bytes for aes-128-gcm |
| hysteria2 / trojan password | arbitrary, 16 chars generated |

`scripts/generate-config.py` prints the derived public key and the verification
in `docs/deploy.md#verify-the-generated-secrets` confirms the key pair is real
(an ECDH round trip), not just random bytes.

## Security notes

- Never commit a rendered `config.json`. `.gitignore` already excludes it.
- `/etc/sing-box/config.json` should stay `0600 root:root`.
- If you publish a masked copy for documentation, mask **entire** values —
  keeping the first and last few characters plus the length still narrows the
  search space considerably.

## License

Configuration and scripts: MIT.

