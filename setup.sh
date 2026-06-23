#!/bin/bash
# PlutoClaw Setup Script
# Mac: ./setup.sh
# Pi : ./setup.sh --pi

echo ""
echo "═══════════════════════════════════════"
echo "  🐾  PlutoClaw Setup"
echo "═══════════════════════════════════════"

PI_MODE=false
if [ "$1" == "--pi" ]; then
  PI_MODE=true
  echo "  Mode: Raspberry Pi"
else
  echo "  Mode: Mac (Development)"
fi
echo ""

# Python dependencies
echo "[1/4] Install Python dependencies..."
pip3 install \
  ultralytics \
  opencv-python \
  fastapi \
  uvicorn \
  pyyaml \
  requests \
  aiofiles \
  python-multipart \
  --quiet

if [ "$PI_MODE" = true ]; then
  echo "      Installing Pi-specific packages..."
  pip3 install RPi.GPIO Adafruit-DHT --break-system-packages --quiet 2>/dev/null || true
fi

echo "      ✅ Python packages siap"

# Node.js WA Bridge
echo "[2/4] Install WA Bridge dependencies..."
cd wa_bridge
npm install \
  @whiskeysockets/baileys \
  express \
  qrcode-terminal \
  pino \
  --save --silent
cd ..
echo "      ✅ WA Bridge siap"

# Buat folder yang dibutuhkan
echo "[3/4] Membuat folder..."
mkdir -p data media/snapshots media/clips wa_bridge/auth models
echo "      ✅ Folder siap"

# Download YOLOv8 model (nano - paling ringan)
echo "[4/4] Download YOLOv8 model..."
python3 -c "
from ultralytics import YOLO
print('      Downloading yolov8n.pt...')
YOLO('yolov8n.pt')
print('      ✅ Model siap')
" 2>/dev/null || echo "      ⚠️  Download model manual: python3 -c \"from ultralytics import YOLO; YOLO('yolov8n.pt')\""

# Auto-start di Pi via systemd
if [ "$PI_MODE" = true ]; then
  echo ""
  echo "[+] Setup auto-start systemd..."
  WORKDIR=$(pwd)
  cat > /tmp/plutoclaw.service << EOF
[Unit]
Description=PlutoClaw Edge AI
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$WORKDIR
ExecStart=/usr/bin/python3 $WORKDIR/main.py
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF
  sudo mv /tmp/plutoclaw.service /etc/systemd/system/
  sudo systemctl daemon-reload
  sudo systemctl enable plutoclaw
  echo "      ✅ Auto-start aktif (sudo systemctl start plutoclaw)"
fi

echo ""
echo "═══════════════════════════════════════"
echo "  Setup selesai!"
echo ""
echo "  Jalankan PlutoClaw:"
echo "    python3 main.py"
echo ""
echo "  WA Bridge (terminal terpisah):"
echo "    cd wa_bridge && node server.js"
echo ""
echo "  Dashboard:"
echo "    http://localhost:8080"
echo "═══════════════════════════════════════"
echo ""
