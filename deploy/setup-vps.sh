#!/bin/bash
# VPS Native Setup Script (no Docker)
# Run as root on Ubuntu 22.04+

set -e

echo "=== Installing system dependencies ==="
apt update && apt upgrade -y
apt install -y python3.11 python3.11-venv python3-pip ffmpeg nginx certbot python3-certbot-nginx

echo "=== Creating app user ==="
useradd -m -s /bin/bash mediacomp || true
mkdir -p /opt/media-compressor
chown mediacomp:mediacomp /opt/media-compressor

echo "=== Setup complete! ==="
echo "Next steps:"
echo "1. Clone your repo to /opt/media-compressor"
echo "2. Run: sudo cp /opt/media-compressor/deploy/media-compressor.service /etc/systemd/system/"
echo "3. Run: sudo systemctl enable --now media-compressor"
