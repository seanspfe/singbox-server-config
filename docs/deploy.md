# Deploying on a new VPS

## READ FIRST: domain and certificate

**Two of the four inbounds will not start without a real TLS certificate, and a
certificate needs a real domain. Confirm these before touching the server.**

| What | Why it is required | What happens if missing |
|---|---|---|
| **A domain** you control | hysteria2 and trojan serve a real TLS certificate, so clients must dial a hostname the certificate covers | both inbounds refuse to start |
| **A DNS A record**: domain -> this server's public IP | `certbot --standalone` validates over HTTP-01, which needs the name to resolve here | certificate issuance fails |
| **TCP 80 open** while issuing | the ACME HTTP-01 challenge arrives on port 80 | certificate issuance fails |
| **Certificate files** at `/opt/certs/fullchain.pem` and `/opt/certs/privkey.pem`, mode `600 root:root` | the paths are hard-coded in the template | `permission denied` on start |

**This is the most common way this deployment fails.** Skipping the domain step
produces a config that looks fine, starts half its inbounds, and leaves
hysteria2 and trojan dead without an obvious error.

VLESS + REALITY does **not** need its own certificate — it borrows the TLS
handshake of `www.microsoft.com`. If you want a certificate-free node, keep
only the VLESS inbound and delete the other three from the template.

Confirm the domain before proceeding:

```bash
DOMAIN=relay.example.com
IP=$(curl -s https://api.ipify.org)
echo "server IP: $IP"
dig +short "$DOMAIN"      # must print the same IP
```

If `dig` does not print the server's IP, fix DNS first. Nothing below works
otherwise.

---

## Overview

Target: a fresh Debian 12/13 or Ubuntu 22.04+ server (x86_64 or arm64) with
root or passwordless sudo.

Run the steps in order. Step 8 gates on `sing-box check`; step 9 verifies the
listeners. If a step fails, stop rather than continuing.

The Tailscale endpoint needs no domain and no certificate. Leave
`--tailscale-key` empty to skip joining a tailnet — the four proxy inbounds
work regardless.

## 1. Install sing-box

```bash
curl -fsSL https://sing-box.app/install.sh | sudo sh
sing-box version
```

Requires **1.11 or newer** for the `tailscale` endpoint type:

```bash
sing-box generate --help | grep -i tailscale
```

## 2. Prepare directories

```bash
sudo mkdir -p /etc/sing-box /var/lib/sing-box /var/log/sing-box
sudo chmod 700 /var/lib/sing-box
```

## 3. Generate the configuration

```bash
sudo apt install -y python3-pip
pip install --break-system-packages cryptography   # or use a venv
sudo python3 scripts/generate-config.py --output /etc/sing-box/config.json \
     --host "$DOMAIN" --tailscale-hostname "$(hostname -s)"
```

This writes **two** files:

| File | Contents |
|---|---|
| `/etc/sing-box/config.json` | the server config, mode `0600` |
| `/etc/sing-box/config.client.txt` | REALITY public key and every client credential, mode `0600` |

The client file exists so the deployment is self-contained: whoever configures
the phone or laptop reads one file instead of scraping console output. It
contains live secrets — keep it at `0600` and do not commit it.

`--host` is recorded in that file and written into the share links. Pass the
domain from step 0.

Then lock the file down:

```bash
sudo chown root:root /etc/sing-box/config.json
sudo chmod 600 /etc/sing-box/config.json
```

## 4. Certificates (hysteria2 + trojan)

Both inbounds read `/opt/certs/fullchain.pem` and `/opt/certs/privkey.pem`.
REALITY does not use these.

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d "$DOMAIN"
sudo mkdir -p /opt/certs
sudo cp "/etc/letsencrypt/live/$DOMAIN/fullchain.pem" /opt/certs/
sudo cp "/etc/letsencrypt/live/$DOMAIN/privkey.pem"   /opt/certs/
sudo chown root:root /opt/certs/*.pem
sudo chmod 600 /opt/certs/privkey.pem
```

If `certbot` fails with `Timeout during connect`, port 80 is blocked or DNS is
wrong — both are covered in the READ FIRST section.

## 5. Firewall

```bash
sudo bash scripts/setup-firewall.sh
```

Installs ufw, allows SSH plus the four service ports, sets inbound default to
deny, and prints the rules.

| Port | Proto | Inbound |
|---|---|---|
| 8443 | tcp | VLESS + REALITY |
| 4443 | udp | hysteria2 |
| 13159 | tcp | trojan |
| 2096 | tcp | shadowsocks 2022 |

**Do not open 9091 or 9999** — API and clash_api, bound to `127.0.0.1` on
purpose.

hysteria2 is **UDP**. Opening it as TCP is the most common mistake and
fails silently.

Once the certificate is issued, port 80 no longer needs to be open.

## 6. BBR and kernel tuning

```bash
sudo bash scripts/setup-bbr.sh
```

Writes `/etc/sysctl.d/99-singbox-tuning.conf`, applies it, and exits non-zero if
BBR did not take effect. Sets `fq` + `bbr`, the socket backlog, the neighbour
table and `fs.file-max`.

## 7. Install the service

```bash
sudo cp systemd/sing-box.service /etc/systemd/system/
sudo systemctl daemon-reload
```

## 8. Validate before starting

```bash
sudo sing-box check -c /etc/sing-box/config.json
echo "exit=$?"
```

Must exit `0` with no output. Do not start the service until it does.

| Message | Cause |
|---|---|
| `unknown field "_meta"` | older generator; regenerate with the current script |
| `read key: permission denied` | `/opt/certs/privkey.pem` permissions |
| `decode config` | malformed JSON; rerun the generator |

## 9. Start and verify

```bash
sudo systemctl enable --now sing-box
sudo systemctl status sing-box --no-pager
journalctl -u sing-box -n 40 --no-pager
```

Must be `active (running)`. Then confirm all four listeners:

```bash
ss -tlnp | grep -E ':8443|:13159|:2096'
ss -ulnp | grep ':4443'
```

A missing listener means that inbound was rejected — re-read `journalctl`.

## 10. Export share links and QR codes

```bash
pip install --break-system-packages segno
python3 scripts/export-subscription.py \
    --config /etc/sing-box/config.json \
    --client-info /etc/sing-box/config.client.txt \
    --out-dir ./sub
```

Passing `--client-info` reads the host and public key from the file written in
step 3, so nothing has to be copied by hand. You can still override either one
with `--host` or `--public-key`.

Produces, in `./sub`:

| File | Contents |
|---|---|
| `links.txt` | one share URI per node, newline separated |
| `subscription.txt` | the same links base64-encoded, for subscription import |
| `vless.png`, `hysteria2.png`, `trojan.png`, `shadowsocks.png` | one QR code per node |
| `subscription.png` | one QR containing the whole subscription |

Scan a node QR with Shadowrocket, Happ, sing-box or v2rayNG to add that single
node. Scan `subscription.png` (or import `subscription.txt`) to add all four at
once.

`--host` is what the client dials: the domain from step 0, or the bare public
IP. **Use the domain** — hysteria2 and trojan certificates do not cover a bare
IP, so those two only work by hostname.

The Tailscale endpoint is never exported: it joins a tailnet, it is not a
client node.

## 11. Client settings (VLESS + REALITY, manual entry)

| Field | Value |
|---|---|
| Address | `$DOMAIN` (or the public IP) |
| Port | 8443 |
| UUID | `inbounds[0].users[0].uuid` |
| Flow | `xtls-rprx-vision` |
| SNI | `www.microsoft.com` |
| Public key | `config.client.txt`, line `pbk` |
| Short ID | `inbounds[0].tls.reality.short_id[0]` |
| Fingerprint | `chrome` |

## Verify the generated secrets

Proves the REALITY key pair is a real X25519 pair (ECDH round trip), not 32
random bytes:

```python
import base64, json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)

PUBLIC_KEY = "PASTE_THE_PUBLIC_KEY_FROM_STEP_3"

cfg = json.load(open("/etc/sing-box/config.json"))
priv = base64.urlsafe_b64decode(
    cfg["inbounds"][0]["tls"]["reality"]["private_key"] + "==")
pub = base64.urlsafe_b64decode(PUBLIC_KEY + "==")

k = X25519PrivateKey.from_private_bytes(priv)
derived = k.public_key().public_bytes(
    serialization.Encoding.Raw, serialization.PublicFormat.Raw)
assert derived == pub, "key pair does not match"

peer = X25519PrivateKey.generate()
assert k.exchange(peer.public_key()) == peer.exchange(
    X25519PublicKey.from_public_bytes(pub))
print("REALITY key pair verified")
```

## Troubleshooting

**Port open, client cannot connect.** Check the protocol — hysteria2 is UDP.
Confirm with `ss -ulnp | grep 4443`.

**`sing-box check` passes, service exits immediately.** Certificate path or
permission problem; `journalctl -u sing-box` names the file.

**Client connects but no traffic.** Verify the short ID matches exactly and the
SNI is `www.microsoft.com`. A mismatch is rejected during the REALITY handshake
with no useful client-side error.

**QR code will not scan.** Regenerate with the current script (PNG output). A
very long subscription can exceed what a single QR comfortably holds; scan the
per-node QR codes instead.

**Tailscale endpoint never comes up.** Pass a key with `--tailscale-key`, or
delete `/var/lib/sing-box/tailscale` and restart to re-register. Leaving the key
empty is fine if you do not need the tailnet.

## Client compatibility warning

REALITY servers on **Xray-core 26.9.8+** require an `X25519MLKEM768` key share in the
ClientHello. sing-box strips that share in `common/tls/reality_client.go`, so
**sing-box clients** fail against newer Xray-backed servers
(SagerNet/sing-box#4520, still open).

This does not affect the server built here: sing-box is the server, and current
sing-box, Xray, Shadowrocket and Happ clients all connect to it. It only
matters when a sing-box client talks to an Xray REALITY server.

