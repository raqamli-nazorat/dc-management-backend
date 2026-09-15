# LiveKit va Django Backend Production Sozlash Qo'llanmasi

Ushbu hujjat haqiqiy serverda (Ubuntu/Debian VPS) **LiveKit Server**, **Systemd servislari**, **Nginx teskari proksi (Reverse Proxy)** va **Firewall (UFW)** ni to'g'ri o'rnatish va sozlash bo'yicha to'liq qo'llanmadir.

---

## 1. Domen masalasi: Bitta domenmi yoki alohida subdomen?

Sizda **2 xil yo'l** bor:

### A varianti: Yagona domen (`backend.raqamlinazorat.uz`)
* Bitta domen orqali ham Django REST API, ham Django Channels (WebSockets), ham LiveKit (Signaling / RTC) ishlaydi.
* Nginx yo'llar (path) bo'yicha ajratadi:
  - `/api/...` va `/ws/...` ➔ Django (Daphne / Gunicorn, 8000-port)
  - `/rtc/...` va `/twirp/...` ➔ LiveKit Server (7880-port)
* **Afzalligi:** Qo'shimcha subdomen ochish va yangi SSL sertifikat olish shart emas.

### B varianti: Alohida subdomen (`meet.raqamlinazorat.uz` yoki `livekit.raqamlinazorat.uz`) — *Tavsiya etiladi*
* Django alohida: `backend.raqamlinazorat.uz` (8000-portga proksi)
* LiveKit alohida: `meet.raqamlinazorat.uz` (7880-portga to'liq proksi)
* **Afzalligi:** Nginx konfiguratsiyasi juda sodda bo'ladi, yo'llar (path) chalkashmaydi, yuklama balansi (load balancing) va xavfsizlik ajratiladi.

> Quyida **ikkala variant** uchun ham tayyor Nginx konfiguratsiyalari keltirilgan.

---

## 2. Serverda LiveKit Serverni o'rnatish

Agar serverda hali LiveKit o'rnatilmagan bo'lsa:

```bash
# Rasmiy o'rnatish skripti orqali yuklab olish
curl -sSL https://get.livekit.io | bash

# O'rnatilganini tekshirish
livekit-server --version
```

---

## 3. Production uchun `livekit.yaml` konfiguratsiyasi

Serveringizda `/opt/livekit/livekit.yaml` yoki loyihangiz papkasidagi `livekit.yaml` faylini quyidagicha sozlang:

```yaml
port: 7880
bind_addresses:
  - ""

rtc:
  tcp_port: 7881
  port_range_start: 50000
  port_range_end: 60000
  # Agar serveringiz NAT ortida (AWS EC2, Hetzner Cloud yoki router ortida) bo'lsa:
  use_external_ip: true

keys:
  APIx52CNCHNzsUy: xKOfMYeyshaD3kVVeCV7izdGfNy6e1fOgkdHIBJLYKvL

webhook:
  api_key: APIx52CNCHNzsUy
  urls:
    - http://127.0.0.1:8000/api/meetings/livekit/webhook/
```

> **Eslatma:** `use_external_ip: true` parametri LiveKit'ga serverning haqiqiy tashqi (public) IP manzilini avtomatik aniqlab, mijozlarga (brauzer va mobil ilovalarga) shu IP orqali video/audio almashishni buyuradi.

---

## 4. LiveKit Serverni Systemd orqali avtomatik ishga tushirish (`systemd service`)

LiveKit server fonda doimiy ishlab turishi, kompyuter/server o'chib yonganda o'zi avtomatik ko'tarilishi va xatolik berib to'xtab qolsa o'zini qayta tiklashi (auto-restart) uchun systemd servisi yaratiladi.

### 1-qadam: Servis faylini yaratish

```bash
sudo nano /etc/systemd/system/livekit.service
```

Quyidagi matnni joylang (fayl yo'lini o'zingizning serveringizdagi `livekit.yaml` joylashuviga moslang):

```ini
[Unit]
Description=LiveKit Server
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/livekit
ExecStart=/usr/local/bin/livekit-server --config /opt/livekit/livekit.yaml
Restart=always
RestartSec=3
LimitNOFILE=65535

[Install]
WantedBy=multi-user.target
```

*(Agar loyiha ichidagi `livekit.yaml` dan foydalanmoqchi bo'lsangiz, `ExecStart=/usr/local/bin/livekit-server --config /home/alijonov/Documents/PycharmProjects/works/Django\ Rest\ Framework/dc-management-backend/livekit.yaml` qilasiz).*

### 2-qadam: Servisni faollashtirish va ishga tushirish

```bash
# Systemd yangilanishlarini o'qish
sudo systemctl daemon-reload

# Xizmatni avto-yuklanishga qo'shish (server yonganda o'zi yonadi)
sudo systemctl enable livekit

# Xizmatni hoziroq ishga tushirish
sudo systemctl start livekit

# Holatini tekshirish
sudo systemctl status livekit
```

### 3-qadam: Servisni boshqarish buyruqlari
```bash
sudo systemctl restart livekit   # Qayta ishga tushirish
sudo systemctl stop livekit      # To'xtatish
sudo journalctl -u livekit -f    # Jonli loglarni ko'rish
```

---

## 5. Nginx Konfiguratsiyasi

### 1-variant: Yagona domen (`backend.raqamlinazorat.uz`)

Ushbu variantda bitta domenga kelgan so'rovlar yo'llar (path) bo'yicha Django va LiveKit o'rtasida taqsimlanadi:

```nginx
server {
    listen 80;
    server_name backend.raqamlinazorat.uz;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name backend.raqamlinazorat.uz;

    ssl_certificate /etc/letsencrypt/live/backend.raqamlinazorat.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backend.raqamlinazorat.uz/privkey.pem;

    client_max_body_size 100M;

    # -------------------------------------------------------------
    # 1. LiveKit Signaling va WebSockets (/rtc/)
    # -------------------------------------------------------------
    location /rtc/ {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # -------------------------------------------------------------
    # 2. LiveKit Twirp RPC API (/twirp/)
    # -------------------------------------------------------------
    location /twirp/ {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    # -------------------------------------------------------------
    # 3. Django WebSockets (/ws/ va /api/ws/)
    # -------------------------------------------------------------
    location ~* ^/(?:api/)?ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }

    # -------------------------------------------------------------
    # 4. Django REST API va Admin (boshqa barcha so'rovlar)
    # -------------------------------------------------------------
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

> **Bu holda `.env` sozlamasi:**
> ```env
> LIVEKIT_URL=wss://backend.raqamlinazorat.uz
> ```

---

### 2-variant: Alohida subdomen (`meet.raqamlinazorat.uz`) — *Tavsiya etiladi*

Agar alohida subdomen ochsangiz, sozlamalar eng toza va professional ko'rinishda bo'ladi:

```nginx
# --- 1. Django Backend (backend.raqamlinazorat.uz) ---
server {
    listen 443 ssl http2;
    server_name backend.raqamlinazorat.uz;

    ssl_certificate /etc/letsencrypt/live/backend.raqamlinazorat.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/backend.raqamlinazorat.uz/privkey.pem;

    client_max_body_size 100M;

    # Django WebSockets
    location ~* ^/(?:api/)?ws/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_read_timeout 86400s;
    }

    # Django HTTP REST API
    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}

# --- 2. LiveKit Meet Server (meet.raqamlinazorat.uz) ---
server {
    listen 443 ssl http2;
    server_name meet.raqamlinazorat.uz;

    ssl_certificate /etc/letsencrypt/live/meet.raqamlinazorat.uz/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/meet.raqamlinazorat.uz/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:7880;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 86400s;
        proxy_send_timeout 86400s;
    }
}
```

> **Bu holda `.env` sozlamasi:**
> ```env
> LIVEKIT_URL=wss://meet.raqamlinazorat.uz
> ```

---

## 6. Server Xavfsizlik Devori (Firewall / UFW) sozlamalari

WebRTC (video va audio) to'g'ri o'tishi uchun serverda quyidagi portlar ochiq bo'lishi **shart**:

```bash
# 1. Standart veb-portlar (Nginx uchun)
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp

# 2. LiveKit WebRTC TCP ulanishi
sudo ufw allow 7881/tcp

# 3. LiveKit WebRTC UDP media portlari (Video va Audio uzatish diapazoni)
sudo ufw allow 50000:60000/udp

# Firewall holatini tekshirish
sudo ufw status verbose
```

> **Eslatma:** Agar siz AWS EC2, Google Cloud yoki Hetzner Cloud ishlatayotgan bo'lsangiz, server konsolidagi (Security Group / Cloud Firewall) qoidalarida ham `UDP 50000-60000` va `TCP 7881` portlariga ruxsat berilgan bo'lishi kerak.

---

## 7. To'liq tekshiruv (Checklist)

1. [ ] LiveKit service ishlayapti: `sudo systemctl status livekit` -> `active (running)`.
2. [ ] Nginx sinovi muvaffaqiyatli: `sudo nginx -t && sudo systemctl reload nginx`.
3. [ ] UFW portlari ochilgan: `sudo ufw status`.
4. [ ] `.env` faylida to'g'ri URL ko'rsatilgan: `LIVEKIT_URL=wss://backend.raqamlinazorat.uz` (yoki `wss://meet.raqamlinazorat.uz`).
5. [ ] Webhook URL to'g'ri ulangan: `livekit.yaml` dagi URL Django webhook manziliga mos.
