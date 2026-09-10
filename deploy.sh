#!/bin/bash
# ================================================================
# Chiroqchi Taksi Bot — Oracle Cloud Ubuntu Deploy Script
# Muallif: Auto-generated
# Ishlatish: bash deploy.sh
# ================================================================

set -e  # Xato bo'lsa to'xtaydi

BOT_DIR="/home/ubuntu/taxibot"
SERVICE_NAME="taxibot"
PYTHON="python3.11"

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║   🚕 CHIROQCHI TAKSI BOT — SERVER DEPLOY        ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. Tizimni yangilash ──────────────────────────────────────
echo "📦 [1/7] Tizim paketlarini yangilash..."
sudo apt-get update -qq
sudo apt-get install -y -qq \
    python3.11 python3.11-venv python3.11-dev \
    python3-pip git curl wget \
    libsqlite3-dev libssl-dev libffi-dev \
    ffmpeg libsm6 libxext6  # easyocr / opencv uchun
echo "✅ Paketlar tayyor."

# ── 2. Bot papkasini yaratish ─────────────────────────────────
echo ""
echo "📁 [2/7] Bot papkasini tayyorlash..."
mkdir -p "$BOT_DIR"
cd "$BOT_DIR"
echo "✅ Papka: $BOT_DIR"

# ── 3. Virtual muhit yaratish ─────────────────────────────────
echo ""
echo "🐍 [3/7] Python virtual muhit yaratish..."
if [ ! -d "venv" ]; then
    $PYTHON -m venv venv
    echo "✅ Yangi venv yaratildi."
else
    echo "ℹ️  venv allaqachon mavjud, o'tkazib yuborildi."
fi

# ── 4. Kutubxonalarni o'rnatish ───────────────────────────────
echo ""
echo "📚 [4/7] Kutubxonalar o'rnatilmoqda (bu biroz vaqt olishi mumkin)..."
venv/bin/pip install --upgrade pip -q
venv/bin/pip install -r requirements.txt -q
echo "✅ Kutubxonalar o'rnatildi."

# ── 5. .env faylini tekshirish ────────────────────────────────
echo ""
echo "🔐 [5/7] .env faylini tekshirish..."
if [ ! -f ".env" ]; then
    echo "⚠️  .env fayli topilmadi!"
    echo "   Quyidagilarni kiriting:"
    read -p "   BOT_TOKEN: " BOT_TOKEN
    read -p "   ADMIN_ID: " ADMIN_ID
    cat > .env << EOF
BOT_TOKEN=$BOT_TOKEN
ADMIN_ID=$ADMIN_ID
DB_PATH=bot.db
USE_PROXY=False
PROXY_URL=
COMMISSION_RATE=10
MIN_DRIVER_BALANCE=20000
EOF
    echo "✅ .env fayli yaratildi."
else
    echo "✅ .env fayli mavjud."
fi
chmod 600 .env

# ── 6. systemd service o'rnatish ─────────────────────────────
echo ""
echo "⚙️  [6/7] systemd service o'rnatilmoqda..."
sudo cp taxibot.service /etc/systemd/system/${SERVICE_NAME}.service
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}
sudo systemctl restart ${SERVICE_NAME}
sleep 2

# ── 7. Holat tekshirish ───────────────────────────────────────
echo ""
echo "🔍 [7/7] Bot holati tekshirilmoqda..."
if sudo systemctl is-active --quiet ${SERVICE_NAME}; then
    echo ""
    echo "╔══════════════════════════════════════════════════╗"
    echo "║   ✅ BOT MUVAFFAQIYATLI ISHGA TUSHDI! 🚀        ║"
    echo "║   24/7 AVTOMATIK ISHLAB TURADI!                  ║"
    echo "╚══════════════════════════════════════════════════╝"
else
    echo "❌ Bot ishga tushmadi! Log tekshirilmoqda..."
    sudo journalctl -u ${SERVICE_NAME} --no-pager -n 20
fi

echo ""
echo "📋 Foydali buyruqlar:"
echo "   sudo systemctl status $SERVICE_NAME    # Holat ko'rish"
echo "   sudo systemctl restart $SERVICE_NAME   # Qayta ishga tushirish"
echo "   sudo systemctl stop $SERVICE_NAME      # To'xtatish"
echo "   sudo journalctl -u $SERVICE_NAME -f    # Jonli log ko'rish"
echo ""
