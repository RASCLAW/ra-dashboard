#!/bin/bash
# Start go2rtc CCTV viewer
# Converts RTSP stream to browser-viewable WebRTC
# Access at: http://localhost:1984

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CONFIG="$SCRIPT_DIR/go2rtc.yaml"

if [ ! -f "$CONFIG" ]; then
    echo "ERROR: go2rtc.yaml not found at $CONFIG"
    exit 1
fi

echo "Starting go2rtc..."
echo "  Stream: bed_cam (Tapo C200)"
echo "  Web UI: http://localhost:1984"
echo "  Direct: http://localhost:1984/stream.html?src=bed_cam"
echo ""

docker run --rm -d \
    --name go2rtc \
    --network host \
    -v "$CONFIG:/config/go2rtc.yaml" \
    alexxit/go2rtc

echo "go2rtc started. Open http://localhost:1984 in your browser."
echo "To stop: docker stop go2rtc"
