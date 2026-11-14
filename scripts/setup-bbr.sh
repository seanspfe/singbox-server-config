# BBR + fq congestion control
#
# Applies on Debian/Ubuntu (systemd-sysctl). Persists across reboots.
# Usage: sudo bash scripts/setup-bbr.sh

set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "run as root" >&2
  exit 1
fi

# The kernel must ship the BBR module (all current Debian/Ubuntu kernels do).
if ! modprobe tcp_bbr 2>/dev/null; then
  echo "warning: tcp_bbr module not available; skipping BBR" >&2
fi

cat > /etc/sysctl.d/99-singbox-tuning.conf <<'EOF'
# BBR congestion control with fq qdisc: better throughput on lossy links.
net.core.default_qdisc = fq
net.ipv4.tcp_congestion_control = bbr

# High connection counts (many clients behind one node).
net.core.somaxconn = 8192
net.ipv4.tcp_max_syn_backlog = 8192

# Keep the neighbour table from overflowing with many peers.
net.ipv4.neigh.default.gc_thresh2 = 8192
net.ipv4.neigh.default.gc_thresh3 = 16384

# Accept and forward efficiently; do not drop valid traffic for filtering.
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2

# Raise file descriptors for a proxy handling many sockets.
fs.file-max = 1048576
EOF

sysctl --system >/dev/null

echo "effective values:"
sysctl -n net.core.default_qdisc net.ipv4.tcp_congestion_control \
        net.core.somaxconn net.ipv4.neigh.default.gc_thresh3 fs.file-max

cc="$(sysctl -n net.ipv4.tcp_congestion_control)"
if [ "$cc" != "bbr" ]; then
  echo "ERROR: congestion control is '$cc', expected bbr" >&2
  exit 1
fi
echo "BBR active"

