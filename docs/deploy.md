# Deploying on a new VPS

Assumes Debian 12/13 or Ubuntu 22.04+ on x86_64 or arm64, root access, and a
domain pointing at the server for the certificate-backed inbounds.

## 1. Install sing-box

```bash
curl -fsSL https://sing-box.app/install.sh | sudo sh
sing-box version
```

The `tailscale` endpoint needs sing-box **1.11 or newer**. Check with
`sing-box generate --help` — it should list `tailscale` support via
`endpoints`.

## 2. Prepare directories

```bash
sudo mkdir -p /etc/sing-box /var/lib/sing-box /var/log/sing-box
sudo chmod 700 /var/lib/sing-box
```

## 3. Generate the configuration

```bash
pip install cryptography
sudo python3 scripts/generate-config.py --output /etc/sing-box/config.json \
     --tailscale-hostname my-node
```

Copy the printed **REALITY public key** — the client needs it.

## 4. Certificates (hysteria2 + trojan)

Both inbounds read `/opt/certs/fullchain.pem` and `/opt/certs/privkey.pem`.
Any ACME client works; this is the minimal certbot path:

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d your.domain.example
sudo mkdir -p /opt/certs
sudo cp /etc/letsencrypt/live/your.domain.example/fullchain.pem /opt/certs/
sudo cp /etc/letsencrypt/live/your.domain.example/privkey.pem /opt/certs/
sudo chmod 600 /opt/certs/privkey.pem
```

REALITY does **not** use these files; it borrows the TLS handshake of
`www.microsoft.com`.

## 5. systemd unit

```bash
sudo cp systemd/sing-box.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sing-box
sudo systemctl status sing-box --no-pager
journalctl -u sing-box -n 30 --no-pager
```

## 6. Firewall

Open only what you use. Note the UDP/TCP split — hysteria2 is UDP, the rest TCP:

```bash
sudo ufw allow 8443/tcp   # VLESS REALITY
sudo ufw allow 4443/udp   # hysteria2
sudo ufw allow 13159/tcp  # trojan
sudo ufw allow 2096/tcp   # shadowsocks 2022
```

Keep `9091` (API) and `9999` (clash_api) bound to loopback. The template
listens on `127.0.0.1` for both; exposing them publicly hands out your control
plane.

## 7. Client side

VLESS + REALITY:

| Field | Value |
|---|---|
| Address | your VPS |
| Port | 8443 |
| UUID | from the generated config |
| Flow | `xtls-rprx-vision` |
| SNI | `www.microsoft.com` |
| Public key | printed by the generator |
| Short ID | `short_id` from the config |
| Fingerprint | `chrome` |

## Verify the generated secrets

Run this after generation. It proves the REALITY key pair is a real X25519
pair (ECDH round trip), not just 32 random bytes:

```python
import json, base64
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)
from cryptography.hazmat.primitives import serialization

cfg = json.load(open("/etc/sing-box/config.json"))
priv = base64.urlsafe_b64decode(
    cfg["inbounds"][0]["tls"]["reality"]["private_key"] + "==")
pub = base64.urlsafe_b64decode(cfg["_meta"]["reality_public_key"] + "==")

k = X25519PrivateKey.from_private_bytes(priv)
derived = k.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw)
assert derived == pub, "key pair does not match"

peer = X25519PrivateKey.generate()
assert k.exchange(peer.public_key()) == peer.exchange(
    X25519PublicKey.from_public_bytes(pub))
print("REALITY key pair verified")
```

## Client compatibility warning

REALITY servers on **Xray-core 26.9.8+** require the client to send an
`X25519MLKEM768` key share in the ClientHello. sing-box strips that share in
`common/tls/reality_client.go`, so sing-box clients fail against newer
Xray-backed servers (SagerNet/sing-box#4520, still open).

On the **sing-box server side** this does not apply — sing-box acts as the
server here, and current sing-box, Xray, Shadowrocket and Happ clients all
connect to it. It only matters when you point sing-box at an Xray REALITY
server.

## Notes

- `short_id` must be even-length hex. An empty list `[]` disables the short id
  check entirely; keep at least one value.
- The tailscale endpoint keeps state in `/var/lib/sing-box/tailscale`. Delete
  that directory and re-run with `--tailscale-key` to re-register the node.
- Blocking BitTorrent is deliberate for a shared VPS; remove the route rule if
  you want it.

