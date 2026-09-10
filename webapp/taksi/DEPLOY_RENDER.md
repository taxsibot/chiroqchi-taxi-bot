# 🚀 Render.com — 100% Bepul 24/7 Serverga Joylash Qo'llanmasi

Ushbu usulda botingiz **Render.com** platformasida mutlaqo bepul ishlaydi va kompyuteringiz o'chsa ham to'xtamaydi!

---

## 1-QADAM: GitHub hisobingizga yuklash

1. **[github.com](https://github.com)** ga kiring (agar hisobingiz bo'lmasa, Google orqali 1 daqiqada oching).
2. O'ng yuqoridagi **"+"** tugmasini bosing ➡️ **"New repository"**.
3. **Repository name:** `chiroqchi-taxi-bot` deb yozing.
4. **"Public"** yoki **"Private"** qoldirib, **"Create repository"** tugmasini bosing.
5. **"uploading an existing file"** havolasini bosing va kompyuteringizdagi bot fayllarini yuklang (papkalari bilan).
6. **Commit changes** tugmasini bosing.

---

## 2-QADAM: Render.com da Botni Ishga Tushirish

1. **[dashboard.render.com](https://dashboard.render.com)** ga kiring.
2. **"Sign in with GitHub"** tugmasini bosing (karta so'ramaydi!).
3. **"New +"** (yuqoridagi ko'k tugma) ➡️ **"Web Service"** ni tanlang.
4. **"Build and deploy from a Git repository"** tanlang va GitHub'dagi `chiroqchi-taxi-bot` loyihangiz yonidagi **"Connect"** tugmasini bosing.
5. Sozlamalar:
   - **Name:** `chiroqchi-taxi-bot`
   - **Region:** `Frankfurt (EU Central)`
   - **Language / Runtime:** `Docker` *(yoki Python 3)*
   - **Instance Type:** `Free` ($0/oy)
6. **Environment Variables** (Maxfiy kalitlar) bo'limiga qo'shing:
   - `BOT_TOKEN` = `botingizning_tokeni`
   - `ADMIN_ID` = `admin_telegram_id`
7. **"Deploy Web Service"** tugmasini bosing!

🎉 **Tayyor!** Render botni o'zi quradi va ishga tushiradi. Sizga maxsus havola beradi (masalan: `https://chiroqchi-taxi-bot.onrender.com`).

---

## 3-QADAM: Botni 24/7 Uxlamaydigan Qilish (UptimeRobot)

Render bepul xizmatlari 15 daqiqa faoliyat bo'lmasa uxlab qolmasligi uchun:

1. **[uptimerobot.com](https://uptimerobot.com)** saytiga kiring (100% bepul).
2. **"Add New Monitor"** tugmasini bosing:
   - **Monitor Type:** `HTTP(s)`
   - **Friendly Name:** `Taxi Bot`
   - **URL (or IP):** Render bergan havolangiz (masalan: `https://chiroqchi-taxi-bot.onrender.com`)
   - **Monitoring Interval:** `Every 5 minutes`
3. **"Create Monitor"** tugmasini bosing.

---

### 🏆 Natija:
- ✅ **UptimeRobot** har 5 daqiqada botingizga signal beradi.
- ✅ Render botingizni **hech qachon o'chirmaydi** va uxlatmaydi.
- ✅ Kompyuteringiz o'chsa ham bot 24/7 ishlab turadi!
