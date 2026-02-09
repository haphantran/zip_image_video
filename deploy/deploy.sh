#!/bin/bash
# Deploy script for native (non-Docker) VPS deployment
# Run from the VPS as the mediacomp user

set -e

cd /opt/media-compressor

echo "=== Pulling latest code ==="
git fetch origin main
git reset --hard origin/main

echo "=== Setting up virtual environment ==="
python3.11 -m venv venv --upgrade
source venv/bin/activate

echo "=== Installing dependencies ==="
pip install --upgrade pip
pip install -r requirements.txt

echo "=== Creating directories ==="
mkdir -p app/uploads app/downloads app/static

echo "=== Restarting service ==="
sudo systemctl restart media-compressor

echo "=== Checking status ==="
sleep 2
sudo systemctl status media-compressor --no-pager

echo "=== Health check ==="
curl -s http://127.0.0.1:8000/health | python3 -m json.tool

echo "=== Deploy complete! ==="
