#!/usr/bin/env bash
# Firewall for the sing-box server
#
# Ports must match templates/config.json.example:
#   8443/tcp   VLESS + REALITY
#   4443/udp   Hysteria2
#   13159/tcp  trojan
#   2096/tcp   shadowsocks 2022
#   80/tcp     ACME HTTP-01, only while obtaining a certificate
#
# 9091 (API) and 9999 (clash_api) stay on loopback and must NOT be opened.
#
# Usage:
#   sudo bash scripts/setup-firewall.sh              # opens 80 for ACME
#   sudo CLOSE_80=1 bash scripts/setup-firewall.sh   # closes 80 afterwards

set -euo pipefail

if ! command -v ufw >/dev/null 2>&1; then
    echo "installing ufw"
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw
fi

# SSH first: enabling ufw without this locks you out.
ufw allow 22/tcp comment ssh

if [ "${CLOSE_80:-0}" = "1" ]; then
    # Port 80 is only needed for the ACME HTTP-01 challenge. Close it once
    # the certificate exists.
    ufw delete allow 80/tcp >/dev/null 2>&1 || true
    echo "port 80 closed"
else
    ufw allow 80/tcp comment "acme http-01, close after issuance"
fi

ufw allow 8443/tcp  comment "vless reality"
ufw allow 4443/udp  comment "hysteria2"
ufw allow 13159/tcp comment "trojan"
ufw allow 2096/tcp  comment "shadowsocks 2022"

ufw default deny incoming
ufw default allow outgoing

# Idempotent: --force skips the interactive prompt when already enabled.
ufw --force enable

echo
ufw status verbose

echo
echo "Reminder: the API (9091) and clash_api (9999) are loopback-only."
echo "If you changed them to 0.0.0.0, close them here or bind them back."

