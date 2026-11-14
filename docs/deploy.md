# Deploying on a new VPS

Target: a fresh Debian 12/13 or Ubuntu 22.04+ server (x86_64 or arm64) with
root or passwordless sudo, and a domain you control for the certificate-backed
inbounds.

Everything below is copy-paste. Run the steps in order; step 8 verifies the
result. If a step fails, stop there rather than continuing.

## 0. Prerequisites

- 1 vCPU / 1 GB RAM is enough (the config in this repo idles around 60 MB).
- A DNS `A` record pointing at the server for the certificate-backed inbounds.
- Ports 80 and 443 open **only while** you obtain the certificate (step 5);
  close them afterwards if nothing else uses them.

## 1. Install sing-box

```bash
curl -fsSL https://sing-box.app/install.sh | sudo sh
sing-box version
```

The `tailscale` endpoint needs **1.11 or newer**. Confirm support:

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
     --tailscale-hostname "$(hostname -s)"
```

The script prints the **REALITY public key** to stderr. Copy it — the client
needs it. It is not stored in the config file.

The file is written with mode `0600`. Verify ownership:

```bash
sudo chown root:root /etc/sing-box/config.json
sudo chmod 600 /etc/sing-box/config.json
```

## 4. Certificates (hysteria2 + trojan)

Both inbounds read `/opt/certs/fullchain.pem` and `/opt/certs/privkey.pem`.
REALITY does **not** use these — it borrows the TLS handshake of
`www.microsoft.com`.

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d relay.example.com
sudo mkdir -p /opt/certs
sudo cp /etc/letsencrypt/live/relay.example.com/fullchain.pem /opt/certs/
sudo cp /etc/letsencrypt/live/relay.example.com/privkey.pem   /opt/certs/
sudo chown root:root /opt/certs/*.pem
sudo chmod 600 /opt/certs/privkey.pem
```

If `sing-box check` later reports `read key: ... permission denied`, the
private key is not readable by the service user — fix the `chmod` above.

## 5. Validate the config

Always run this before starting the service:

```bash
sudo sing-box check -c /etc/sing-box/config.json
```

It must exit **silently**. A `FATAL` line means the config was rejected —
fix that before continuing. Common causes:

| Message | Meaning |
|---|---|
| `unknown field "_meta"` | you are running an older generator; regenerate |
| `read key: permission denied` | `/opt/certs/privkey.pem` not readable |
| `decode config` | malformed JSON — rerun the generator |

## 6. Firewall

```bash
sudo bash scripts/setup-firewall.sh
```

It installs `ufw`, allows 22 plus the four service ports, sets the default
inbound policy to deny, and prints the resulting rules. Ports and protocols:

| Port | Proto | Inbound |
|---|---|---|
| 8443 | tcp | VLESS + REALITY |
| 4443 | udp | hysteria2 |
| 13159 | tcp | trojan |
| 2096 | tcp | shadowsocks 2022 |

**Do not open 9091 or 9999.** Those are the API and clash_api; the template
binds them to `127.0.0.1` deliberately.

Hysteria2 is **UDP** — opening it as TCP is the most common mistake and
produces a perfectly silent failure.

## 7. BBR and kernel tuning

```bash
sudo bash scripts/setup-bbr.sh
```

Writes `/etc/sysctl.d/99-singbox-tuning.conf`, applies it, and exits non-zero
if BBR did not actually take effect. It sets `fq` + `bbr`, raises the socket
backlog, the neighbour table and `fs.file-max`.

## 8. Start and verify

```bash
sudo cp systemd/sing-box.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now sing-box
sudo systemctl status sing-box --no-pager
journalctl -u sing-box -n 40 --no-pager
```

The service must be `active (running)`. Then check the listeners:

```bash
ss -tlnp | grep -E ':8443|:13159|:2096'
ss -ulnp | grep ':4443'
```

All four must be present. If one is missing, sing-box rejected that inbound —
re-read `journalctl`.

## 9. Client settings (VLESS + REALITY)

| Field | Value |
|---|---|
| Address | your VPS |
| Port | 8443 |
| UUID | `inbounds[0].users[0].uuid` from the generated config |
| Flow | `xtls-rprx-vision` |
| SNI | `www.microsoft.com` |
| Public key | printed by the generator |
| Short ID | `inbounds[0].tls.reality.short_id[0]` |
| Fingerprint | `chrome` |

For the other inbounds, read the password from the config and use the domain
your certificate covers.

## Verify the generated secrets

Run this to prove the REALITY key pair is a real X25519 pair (an ECDH round
trip), not just 32 random bytes. It reads the public key from the generator's
output, so keep that value.

```python
import base64, json

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.x25519 import (
    X25519PrivateKey, X25519PublicKey)

PUBLIC_KEY = "PASTE_THE_PUBLIC_KEY_HERE"

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

**Port open but the client cannot connect.**
Check the protocol: hysteria2 is UDP. Then confirm the process is
listening with `ss -ulnp | grep 4443`.

**`sing-box check` passes but the service exits immediately.**
Usually a certificate path or permission problem. `journalctl -u sing-box`
names the file.

**Client connects, no traffic.**
Verify the short ID matches exactly, and that the SNI is `www.microsoft.com`
— a mismatch is rejected during the REALITY handshake with no useful client
error.

**Tailscale endpoint never comes up.**
Generate a key with `tailscale up --authkey` style scopes and pass it with
`--tailscale-key`, or delete `/var/lib/sing-box/tailscale` and restart to
re-register.

## Client compatibility warning

REALITY servers on **Xray-core 26.9.8+** require an `X25519MLKEM768` key share in
the ClientHello. sing-box strips that share in
`common/tls/reality_client.go`, so **sing-box clients** fail against newer
Xray-backed servers (SagerNet/sing-box#4520, still open).

This does not apply to the server built here: sing-box acts as the server, and
current sing-box, Xray, Shadowrocket and Happ clients all connect to it. It
only matters if you point a sing-box client at an Xray REALITY server.

