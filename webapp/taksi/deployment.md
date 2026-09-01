# 🚀 Serverga o'rnatish qo'llanmasi (Deployment Guide)

Ushbu qo'llanma botni Linux (Ubuntu/Debian) serveriga o'rnatish uchun mo'ljallangan.

## 1. Tayyorgarlik

Serverga Python 3 va pip o'rnatilganligiga ishonch hosil qiling:
```bash
sudo apt update
sudo apt install python3 python3-pip git
```

## 2. Loyihani yuklash

Kodni serverga yuklang (masalan, `/root/bot-yangi-dezay` papkasiga):
```bash
cd /root
git clone <Sizning_Repo_Manzilingiz> bot-yangi-dezay
cd bot-yangi-dezay
```

## 3. Kutubxonalarni o'rnatish

```bash
pip3 install -r requirements.txt
```

## 4. Konfiguratsiya (.env)

`.env.example` faylidan nusxa olib, o'zingizning ma'lumotlaringizni kiriting:
```bash
cp .env.example .env
nano .env
```
Fayl ichiga `BOT_TOKEN` va `ADMIN_ID` larni yozing.

## 5. Avtomatik ishlatish (Systemd)

Botni servis sifatida ro'yxatdan o'tkazamiz:
```bash
sudo cp taxibot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable taxibot
sudo systemctl start taxibot
```

## 6. Monitoring (Kuzatish)

Botning holatini va loglarini ko'rish:
```bash
# Servis holati
sudo systemctl status taxibot

# Loglarni jonli ko'rish
tail -f bot.log
```

---
> [!IMPORTANT]
> **Tibbiy Eslatma**: Agar serveringiz RAM xotirasi 1GB dan kam bo'lsa, `easyocr` (Mashina raqamini aniqlash) funksiyasi serverni qotirishi mumkin. Bunday holda swap-xotira qo'shish tavsiya etiladi.

> [!TIP]
> Botni yangilaganingizdan so'ng har doim servisni qayta ishga tushiring: `sudo systemctl restart taxibot`
