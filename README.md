# sing-box server config

A production-shaped **sing-box server** configuration for a single VPS:
VLESS + REALITY + Vision, Hysteria2, Trojan, and Shadowsocks 2022, plus an
embedded Tailscale endpoint — all in one process.

The committed template contains **no real credentials**. Every secret is a
placeholder; `scripts/generate-config.py` fills them in with correctly sized
random values for you.

## Requirements

Read this before running anything. Two of the four inbounds are **blocking** on
infrastructure you must provide.

| Requirement | Needed by | If missing |
|---|---|---|
| **A domain** you control | hysteria2, trojan | those two inbounds refuse to start |
| **DNS A record**: domain -> server public IP | certificate issuance | `certbot` fails |
| **TCP 80 open** while issuing | ACME HTTP-01 | certificate issuance fails |
| **A certificate** at `/opt/certs/` | hysteria2, trojan | `permission denied` on start |
| Linux server with systemd, root or sudo | everything | n/a |
| sing-box **1.11+** | `tailscale` endpoint | endpoint type is rejected |

VLESS + REALITY needs **no domain and no certificate** — it borrows the TLS
handshake of `www.microsoft.com`. If you want a certificate-free node, keep
only that inbound.

The Tailscale auth key is optional: leave `--tailscale-key` empty and the
endpoint simply does not join a tailnet.

Full detail, including what each failure looks like:
[docs/deploy.md](docs/deploy.md#read-first-domain-and-certificate).

**If you are an AI agent doing the deployment:** read
[docs/deploy.md](docs/deploy.md#what-the-operator-must-supply) first, then ask
the operator for the six inputs it lists: server access, domain, DNS, cloud
security group access, certificate choice, and optionally a Tailscale key.
Do not invent credentials — the generator creates them. Do not swap the
domain for a bare IP: hy2 and trojan certificates do not cover an IP address.

**If you are the operator:** a request like "deploy
seanspfe/singbox-server-config on my VPS" is enough only once you can hand over
the domain and access to the cloud console.

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

## Files

| Path | Purpose |
|---|---|
| `templates/config.json.example` | the config, all credentials as placeholders |
| `scripts/generate-config.py` | renders the template, and writes `config.client.txt` with the client credentials |
| `scripts/export-subscription.py` | share links, base64 subscription, PNG QR codes |
| `scripts/setup-firewall.sh` | ufw rules for the four service ports |
| `scripts/setup-bbr.sh` | fq + bbr and kernel tuning, fails if BBR is inactive |
| `scripts/mask-config.py` | masked copy for publication (whole-value replacement) |
| `systemd/sing-box.service` | service unit |
| `docs/deploy.md` | ordered deployment steps |
| `docs/config.masked.json` | masked example of a real deployment |

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

Then export share links and QR codes for every node:

```bash
pip install segno
python3 scripts/export-subscription.py --config /etc/sing-box/config.json     --client-info /etc/sing-box/config.client.txt --out-dir ./sub
```

That writes per-node share URIs, a base64 subscription and one PNG QR code per
node. `generate-config.py` also writes `config.client.txt` (mode `0600`) with the
REALITY public key and every client credential, so the export step needs no
hand-copied values. Scan them with Shadowrocket, Happ, sing-box or v2rayNG.

**A domain is required** for the hysteria2 and trojan inbounds: they serve a
real TLS certificate, and a certificate needs a hostname that resolves to the
server. VLESS + REALITY needs none. Read
[docs/deploy.md](docs/deploy.md#read-first-domain-and-certificate) before
starting.

The Tailscale endpoint is optional. Leave `--tailscale-key` empty and it simply
does not join a tailnet; the four proxy inbounds are unaffected.

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

