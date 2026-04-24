# Notification and WebSocket Integration Guide

Ushbu tizim real-vaqt rejimida (WebSocket) va bildirishnomalar (FCM) bilan ishlash uchun mo'ljallangan. Barcha kanallar (WS va FCM) bir xil ma'lumot modelidan foydalanadi.

## 1. WebSocket Authentication (Ticket System)

WebSocket-ga ulanish xavfsizlik nuqtai nazaridan bir martalik bilet (One-time Ticket) orqali amalga oshiriladi.

**Endpoint:** `POST /api/notifications/tickets/`  
**Headers:** `Authorization: Bearer <JWT_TOKEN>`

**Response:**
```json
{
  "success": true,
  "data": {
    "ticket": "550e8400-e29b-41d4-a716-446655440000",
    "expires_in": 60
  },
  "error": null
}
```

**Connection URL:** `ws://domain.com/ws/notifications/?ticket={ticket_qiymati}`

---

## 2. FCM Device Registration

Mobil qurilmalarga Push bildirishnomalar yuborish uchun FCM tokenni ro'yxatdan o'tkazish talab etiladi.

**Endpoint:** `POST /api/devices/register/`  
**Headers:** `Authorization: Bearer <JWT_TOKEN>`  
**Body:**
```json
{
  "fcm_token": "fcm_token_string",
  "device_id": "unique_id",
  "device_type": "android" // yoki "ios"
}
```

---

## 3. Data Structure (Standard Notification Model)

WebSocket (to'g'ridan-to'g'ri) va FCM (payload ichida) quyidagi formatdagi JSON obyektini qaytaradi:

```json
{
  "id": 15,
  "title": "Vazifa muddati o'tdi",
  "message": "Backend optimization vazifasi kechikmoqda.",
  "type": "alert",
  "extra_data": {
    "action": "open_task", // yoki "open_project"
    "task_id": 45
  },
  "created_at": "2026-04-13T16:00:00.000000"
}
```

### Kanal farqlari:
* **WebSocket:** Ma'lumot yuqoridagi formatda to'g'ridan-to'g'ri keladi.
* **FCM (Push):** Ma'lumot `data['payload']` kaliti ichida JSON-string holatida keladi. Uni avval `json.decode()` qilish lozim.

---

## 4. Notification API

| Vazifa | Metod | Endpoint |
| :--- | :--- | :--- |
| Bildirishnomalar ro'yxati | GET | `/api/notifications/` |
| Xabarni o'qildi deb belgilash | PATCH | `/api/notifications/{id}/read/` |
| Barcha xabarlarni o'qildi qilish | POST | `/api/notifications/read-all/` |