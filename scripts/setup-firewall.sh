# Firewall for the sing-box server
#
# Ports must match templates/config.json.example:
#   8443/tcp   VLESS + REALITY
#   4443/udp   hysteria2
#   13159/tcp  trojan
#   2096/tcp   shadowsocks 2022
#
# 9091 (API) and 9999 (clash_api) stay on loopback and must NOT be opened.
#
# Usage: sudo bash scripts/setup-firewall.sh

set -euo pipefail

if ! command -v ufw >/dev/null 2>&1; then
  echo "installing ufw"
  apt-get update -qq
  DEBIAN_FRONTEND=noninteractive apt-get install -y -qq ufw
fi

# SSH first: enabling ufw without this locks you out.
ufw allow 22/tcp comment 'ssh'

ufw allow 8443/tcp  comment 'vless reality'
ufw allow 4443/udp  comment 'hysteria2'
ufw allow 13159/tcp comment 'trojan'
ufw allow 2096/tcp  comment 'shadowsocks 2022'

ufw default deny incoming
ufw default allow outgoing

# Idempotent: --force skips the interactive prompt when already enabled.
ufw --force enable

echo
ufw status verbose

echo
echo "Reminder: the API (9091) and clash_api (9999) are loopback-only."
echo "If you changed them to 0.0.0.0, close them here or bind them back to 127.0.0.1."

