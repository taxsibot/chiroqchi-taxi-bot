# 🚕 CHIROQCHI TAKSI BOT — Oracle Cloud Bepul Server Qo'llanmasi

> **Oracle Cloud Always Free** — hech qachon pul to'lamasdan abadiy ishlaydi  
> **Resurslar:** 4 OCPU + 24 GB RAM + 200 GB Disk — juda kuchli!

---

## 📋 MUHIM FAYLLAR

| Fayl | Maqsad |
|------|--------|
| `deploy.sh` | Serverga avtomatik o'rnatish skripti |
| `taxibot.service` | Bot 24/7 ishlab turishi uchun systemd konfiguratsiyasi |
| `.env` | Maxfiy kalitlar (token, admin ID) |
| `requirements.txt` | Python kutubxonalar ro'yxati |

---

## 1️⃣ ORACLE CLOUD HISOB OCHISH (bepul)

1. **https://cloud.oracle.com** ga boring
2. **"Start for free"** tugmasini bosing
3. Kredit karta kiritiladi (lekin **hech qanday to'lov bo'lmaydi**)
4. Tasdiqlash SMS/email orqali keladi

---

## 2️⃣ VIRTUAL MASHINA YARATISH

Oracle Console → **Compute → Instances → Create Instance**

| Sozlama | Qiymat |
|---------|--------|
| **Name** | `taxibot-server` |
| **Image** | `Ubuntu 22.04 LTS` |
| **Shape** | `VM.Standard.A1.Flex` |
| **OCPU** | `2` |
| **RAM** | `12 GB` |
| **Disk** | `50 GB` |
| **Network** | Default VCN |

### 🔑 SSH Kalit
- **"Generate a key pair for me"** tanlab SSH kalitni yuklab oling
- Fayl nomi: `ssh-key-taxibot.key`
- Bu fayl kompyuterda xavfsiz saqlaning!

### ✅ Instance yaratilganda
Holat: **RUNNING** bo'lishi kerak (1-2 daqiqa kerak)

---

## 3️⃣ FIREWALL (Port ochish)

Oracle Console → **Networking → Virtual Cloud Networks → Default VCN → Security Lists → Default Security List**

**Ingress Rules ga qo'shing:**
```
Source: 0.0.0.0/0
IP Protocol: TCP
Destination Port: 22  (SSH uchun — allaqachon mavjud bo'lishi mumkin)
```

Server ichida ham firewall ochish:
```bash
sudo iptables -I INPUT -p tcp --dport 22 -j ACCEPT
sudo netfilter-persistent save
```

---

## 4️⃣ SERVERGA ULANISH (SSH)

Windows da **PowerShell** yoki **Git Bash** orqali:
```powershell
# Kalit huquqlarini o'rnatish (bir marta bajarish kerak)
icacls "C:\Users\user\Downloads\ssh-key-taxibot.key" /inheritance:r /grant:r "%username%:R"

# Serverga ulanish
ssh -i "C:\Users\user\Downloads\ssh-key-taxibot.key" ubuntu@<SERVER_IP>
```

> `<SERVER_IP>` ni Oracle Console dagi **Public IP address** bilan almashtiring

---

## 5️⃣ BOT FAYLLARINI SERVERGA YUBORISH

**Usul A — SCP (fayllarni to'g'ridan yuborish):**
```powershell
# Kompyuteringizda bajarish (bot papkasida turib)
scp -i "C:\Users\user\Downloads\ssh-key-taxibot.key" -r "E:\Botlarim\bot yangi dezay\*" ubuntu@<SERVER_IP>:/home/ubuntu/taxibot/
```

**Usul B — Git orqali (tavsiya etiladi):**
```bash
# Serverda bajarish
cd /home/ubuntu
git clone https://github.com/SIZNING_GITHUB/taxibot.git taxibot
```

---

## 6️⃣ AVTOMATIK DEPLOY (1 BUYRUQ)

Serverga ulangandan keyin:
```bash
cd /home/ubuntu/taxibot
chmod +x deploy.sh
bash deploy.sh
```

Skript o'zi so'raydi:
```
BOT_TOKEN: 12345678:ABCdef...
ADMIN_ID: 123456789
```

---

## 7️⃣ BOT HOLATINI TEKSHIRISH

```bash
# Bot ishlayaptimi?
sudo systemctl status taxibot

# Jonli log (real-time)
sudo journalctl -u taxibot -f

# So'nggi 50 ta log qatori
sudo journalctl -u taxibot -n 50
```

---

## 🔄 KODNI YANGILASH (Update)

```bash
cd /home/ubuntu/taxibot

# Fayllarni yangilash (Git bilan)
git pull

# Yoki SCP bilan yangi fayllarni yuborish, keyin:
sudo systemctl restart taxibot

echo "✅ Bot yangilandi va qayta ishga tushdi!"
```

---

## 🛟 MUAMMO YECHISH

| Muammo | Yechim |
|--------|--------|
| Bot ishlamayapti | `sudo journalctl -u taxibot -n 30` log ko'ring |
| Token xato | `.env` faylidagi `BOT_TOKEN` ni tekshiring |
| ModuleNotFoundError | `venv/bin/pip install -r requirements.txt` ni qayta ishlatng |
| Serverga ulab bo'lmayapti | Oracle Console → Security List → Port 22 ochiqmi? |

---

## 💡 FOYDALI BUYRUQLAR

```bash
sudo systemctl start taxibot      # Ishga tushirish
sudo systemctl stop taxibot       # To'xtatish
sudo systemctl restart taxibot    # Qayta ishga tushirish
sudo systemctl enable taxibot     # Avtomatik start (server qayta yoqilganda)
sudo systemctl disable taxibot    # Avtomatik startni o'chirish

# Disk holati
df -h

# RAM holati
free -h

# Jarayonlar
htop
```

---

## 🎯 YAKUNIY NATIJA

```
✅ Bot 24/7 ishlaydi
✅ Server qayta yoqilsa — bot avtomatik ishga tushadi
✅ Crash bo'lsa — 5 soniyada o'zi qayta ishga tushadi
✅ Oyiga $0 to'lov
✅ 4 OCPU + 24GB RAM resurslar
```

---

> 💡 **Tip:** `bot.db` bazani muntazam zaxiralash uchun cron job qo'shing:
> ```bash
> crontab -e
> # Har kuni kechasi soat 03:00 da backup
> 0 3 * * * cp /home/ubuntu/taxibot/bot.db /home/ubuntu/backup/bot_$(date +%Y%m%d).db
> ```
