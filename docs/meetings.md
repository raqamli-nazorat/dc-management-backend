# LiveKit Video Konferensiya va WebSocket Integratsiya Qo'llanmasi (Frontend va Mobile uchun)

Ushbu hujjat **Mobile (Flutter)** va **Frontend (React/Web)** dasturchilari uchun LiveKit hamda Django Channels (WebSocket) orqali video konferensiya funksiyalarini bir xilda, xavfsiz va to'liq integratsiya qilish bo'yicha yagona texnik qo'llanmadir.

---

## 1. Umumiy Arxitektura va Qatlamlar

Video yig'ilish tizimi 3 ta asosiy qatlamga bo'lingan:

```text
1. REST API
   ├── Yig'ilishlar ro'yxati va CRUD (/api/meetings/)
   ├── Deep-link bo'yicha qidiruv (/api/meetings/?uid=MT-0009)
   ├── Yig'ilishni yakunlash (/api/meetings/{id}/close/)
   ├── Davomat va sabab bildirish (/api/meeting-attendance/)
   └── Bir martalik WebSocket bileti (Ticket) olish (/api/notifications/tickets/)

2. Django Channels WebSocket (/api/ws/meetings/{meeting_id}/?ticket={ticket})
   ├── Xona holatini sinxronlash (meeting_state)
   ├── Kutish zali va mezbon tasdig'i (Waiting Room & Knock/Admit)
   ├── Qo'l ko'tarish holati (Hand Raise)
   ├── Jonli emojilar (Reactions)
   ├── Mezbon boshqaruvi (Mute Microphone / Camera)
   └── Ovozni qayta yoqish so'rovi (Unmute Request)

3. LiveKit WebRTC Server (Audio / Video / Screen Share)
   ├── Ovoz, video va ekran ulashish
   └── Jonli guruh chati (LiveKit Data Channel orqali)
```

---

## 2. Autentifikatsiya va WebSocket'ga Ulanish

Barcha WebSocket ulanishlari xavfsiz **bir martalik bilet (One-time Ticket)** orqali ulanadi.

### 1-qadam: Ticket olish (REST API)
* **URL:** `POST /api/notifications/tickets/`
* **Headers:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
* **Response (200 OK):**
```json
{
  "ticket": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
  "expires_in": 60
}
```

### 2-qadam: WebSocket'ga ulanish
Olingan ticket orqali yig'ilishning maxsus kanaliga ulanasiz:
```text
wss://backend.raqamlinazorat.uz/api/ws/meetings/<meeting_id>/?ticket=<ticket>
```
*(Lokal muhitda: `ws://127.0.0.1:8000/api/ws/meetings/16/?ticket=...`)*

> [!IMPORTANT]
> **Web va Mobile uchun qoidalar:**
> 1. URL har doim `wss://` (lokalda `ws://`) va `/api/ws/meetings/{id}/` ko'rinishida bo'lishi shart.
> 2. Ticket bir martalik: WebSocket ulanishi muvaffaqiyatli bo'lishi bilanoq backend uni keshdan o'chiradi. Har bir yangi ulanish yoki qayta ulanish (reconnect) paytida albatta yangi ticket olinishi kerak.
> 3. Ushbu WebSocket faqat yig'ilish xonasi sahifasida (ekranida) faol bo'ladi. Xonadan chiqilganda yoki yig'ilish tugaganda `socket.close()` qilinishi shart!

---

## 3. Ulanish Xatoliklari (Terminal Errors)

Agar foydalanuvchi xonaga kira olmasa, server ulanishni yopishdan oldin `error` xabarini yuboradi:

```json
{
  "type": "error",
  "code": 403,
  "message": "Siz ushbu yig'ilish qatnashchisi emassiz."
}
```

| HTTP / Error Code | WebSocket Close Code | Sabab va Harakat |
| :--- | :--- | :--- |
| `401` | `4003` | Ticket yaroqsiz yoki avtorizatsiyadan o'tilmagan. Yangi ticket olib qayta urinish kerak. |
| `403` | `4003` | Foydalanuvchi ushbu yig'ilish ro'yxatida yo'q. Qayta ulanish to'xtatiladi, xatolik ko'rsatiladi. |
| `404` | `4004` | Yig'ilish allaqachon yakunlangan yoki mavjud emas. Sahifadan chiqiladi. |

---

## 4. Boshlang'ich Holat (`meeting_state`)

Foydalanuvchi muvaffaqiyatli ulanganda server avtomatik tarzda `meeting_state` xabarini yuboradi:

```json
{
  "type": "meeting_state",
  "meeting_id": 16,
  "title": "Haftalik tahlil",
  "requires_approval": true,
  "organizer_joined": true,
  "is_host": true,
  "is_approved": true,
  "token": "eyJhbGciOiJIUzI1Ni...",
  "server_url": "wss://livekit.example.com",
  "room_name": "MT-0009",
  "raised_hands": [
    {
      "user_id": 45,
      "username": "ali",
      "full_name": "Ali Valiyev",
      "raised_at": "2026-09-23T15:30:00Z"
    }
  ]
}
```

* `is_host`: Foydalanuvchi tashkilotchi bo'lsa yoki yig'ilish a'zosi bo'lgan Admin/Menejer bo'lsa `true`.
* `token`: Agar xonaga to'g'ridan-to'g'ri kirish mumkin bo'lsa (mezbon bo'lsa yoki tasdiq talab etilmasa), LiveKit JWT tokeni darhol shu yerda keladi.
* `raised_hands`: Hozirda qo'lini ko'tarib turgan ishtirokchilar ro'yxati (xona ochilganda ekranda ko'rsatish uchun).

---

## 5. Kutish Zali va Mezbon Tasdig'i (Knock & Admit)

Agar `requires_approval: true` bo'lsa va oddiy qatnashchi kirmagan bo'lsa (`is_host: false, is_approved: false`):

### 1-bosqich: Mezbon hali kirmagan bo'lsa
* Serverdan `waiting_organizer` keladi. Ekranda *"Mezbon kirishini kuting"* ko'rsatiladi.
* Mezbon kirishi bilan server barchaga `organizer_joined` xabarini yuboradi.

### 2-bosqich: Xodim kirishni so'rashi (Knock)
Foydalanuvchi ekranda *"Kirishni so'rash"* tugmasini bosganda:
```json
// Client -> Server
{
  "action": "ask_to_join"
}
```

### 3-bosqich: Mezbon ekraniga bildirishnoma borishi
Mezbon(lar) ekranida quyidagi hodisa chiqadi:
```json
// Server -> Host
{
  "type": "knock_request",
  "meeting_id": 16,
  "user_id": 45,
  "username": "ali",
  "full_name": "Ali Valiyev",
  "avatar": "/media/avatars/ali.jpg"
}
```

### 4-bosqich: Mezbon qarori (Admit)
Mezbon qabul qilganda yoki rad etganda:
```json
// Host -> Server
{
  "action": "admit",
  "user_id": 45,
  "decision": "approve" // yoki "reject"
}
```

> [!WARNING]
> Web va Mobile admit so'rovini **faqat WebSocket** orqali yuborishi kerak. REST API orqali parallel so'rov yuborilmaydi.

### 5-bosqich: Foydalanuvchiga javob borishi (`knock_response`)
* **Agar qabul qilinsa (`status: "approved"`):**
```json
{
  "type": "knock_response",
  "status": "approved",
  "server_url": "wss://livekit.example.com",
  "room_name": "MT-0009",
  "token": "eyJhbGciOiJIUzI1Ni..."
}
```
Klient olingan `token` va `server_url` orqali LiveKit xonasiga ulanadi.
* **Agar rad etilsa (`status: "rejected"`):**
```json
{
  "type": "knock_response",
  "status": "rejected",
  "message": "Mezbon yig'ilishga kirishingizni rad etdi."
}
```

---

## 6. Qo'l Ko'tarish (Hand Raise)

Qo'l ko'tarish — bu **holat (state)** hisoblanadi. Har bir ishtirokchi o'z qo'lini ko'tarishi va o'zi tushirishi mumkin.

### 1. Qo'l ko'tarish yoki tushirish:
```json
// Client -> Server
{
  "action": "hand_raise",
  "raised": true // Qo'l ko'tarish uchun true, tushirish uchun false
}
```

### 2. Barchaga boradigan xabar:
Server barcha ishtirokchilarga holat o'zgarganini xabar qiladi:
```json
// Server -> All Clients
{
  "type": "hand_raise_updated",
  "user_id": 45,
  "username": "ali",
  "full_name": "Ali Valiyev",
  "raised": true,
  "raised_at": "2026-09-23T15:40:00Z"
}
```

---

## 7. Jonli Emojilar (Reactions)

Reaksiyalar — bu **bir lahzalik hodisa (ephemeral event)**. Holat saqlanmaydi, faqat ekranda uchib chiquvchi animatsiya ko'rsatiladi.

### 1. Reaksiya yuborish:
```json
// Client -> Server
{
  "action": "send_reaction",
  "reaction": "👏" // Masalan: "👏", "👍", "❤️", "🎉", "🔥"
}
```

### 2. Barcha ishtirokchilarga keladigan xabar:
```json
// Server -> All Clients
{
  "type": "reaction_received",
  "user_id": 45,
  "username": "ali",
  "full_name": "Ali Valiyev",
  "reaction": "👏",
  "sent_at": "2026-09-23T15:40:12Z"
}
```
Mobil va Web ilovalar ushbu xabar kelganda ekranda 2-3 soniyalik emoji animatsiyasini chiqarib so'ndiradi.

---

## 8. Mezbon Moderatsiyasi (Mute & Unmute)

Qatnashchilarni masofadan boshqarish to'liq **Backend va LiveKit Server** orqali boshqariladi. Client-side soxtalashtirishlarga yo'l qo'yilmaydi.

### A. Ishtirokchini majburiy MUTE qilish (Mikrofon yoki Kamera)
Faqat mezbon boshqa ishtirokchining mikrofonini yoki kamerasini o'chira oladi:

```json
// Host -> Server
{
  "action": "moderate_track",
  "target_identity": "45_ab12cd", // LiveKit participant identity
  "track_source": "microphone",   // yoki "camera"
  "operation": "mute"
}
```
**Natija:**
1. Backend LiveKit serverida trackni server darajasida o'chiradi.
2. Barcha qatnashchilarga hodisa boradi:
```json
// Server -> All Clients
{
  "type": "track_moderation_changed",
  "meeting_id": 16,
  "target_identity": "45_ab12cd",
  "user_id": 45,
  "track_source": "microphone",
  "muted": true,
  "actor_user_id": 1
}
```
3. Klient ushbu xabarni olganda, o'sha foydalanuvchining mikrofon/kamera belgisini o'chirilgan (qizil) holatga o'tkazadi.

### B. Ishtirokchiga UNMUTE so'rovini yuborish
Mezbon hech kimning mikrofonini yoki kamerasini uning ruxsatisiz majburiy yoqib yubora olmaydi. Mezbon faqat so'rov yuboradi:

```json
// Host -> Server
{
  "action": "request_track_unmute",
  "target_identity": "45_ab12cd",
  "target_user_id": 45,
  "track_source": "microphone" // yoki "camera"
}
```

**Target ishtirokchiga keladigan taklif:**
```json
// Server -> Target User
{
  "type": "track_unmute_requested",
  "request_id": "b6e3f4e1-...",
  "from_user_id": 1,
  "from_name": "Mezbon Ali",
  "target_identity": "45_ab12cd",
  "track_source": "microphone"
}
```
Foydalanuvchi ekranda: *"Mezbon mikrofoningizni yoqishingizni so'ramoqda: [Roziman] / [Rad etish]"* dialogini ko'radi.

Agar foydalanuvchi **[Roziman]** ni bossa:
1. Uning qurilmasi (Mobile/Web) LiveKit orqali o'z mikrofonini yoqadi:
   `room.localParticipant.setMicrophoneEnabled(true)`
2. Mezbonga tasdiq xabarini qaytaradi:
```json
// Target -> Server
{
  "action": "respond_track_unmute_request",
  "request_id": "b6e3f4e1-...",
  "decision": "accept", // yoki "reject"
  "target_identity": "45_ab12cd",
  "track_source": "microphone"
}
```

---

## 9. LiveKit Chat (Guruh Chati)

Guruh chati LiveKit-ning o'zida mavjud bo'lib, alohida backend ma'lumotlar bazasida saqlash talab etilmaydi. LiveKit Data Channel orqali 0 ms kechikish bilan barcha qatnashchilarga uzatiladi:

```typescript
// Web / Mobile yuborish
const chatMessage = {
  version: 1,
  type: "chat",
  message_id: uuidv4(),
  sender_identity: room.localParticipant.identity,
  sender_name: currentUserName,
  sent_at: new Date().toISOString(),
  text: "Salom barchaga!"
};

const payload = new TextEncoder().encode(JSON.stringify(chatMessage));
await room.localParticipant.publishData(payload, { reliable: true });
```

---

## 10. Multi-Device (Bir nechta qurilmadan kirish)

Foydalanuvchi bitta hisob bilan bir vaqtning o'zida telefonidan ham, kompyuteridan ham kira oladi (biri ikkinchisini uzib yubormaydi).
Token so'rashda ixtiyoriy ravishda qurilma nomini ko'rsatish mumkin:
```json
{
  "action": "get_token",
  "device_id": "phone_samsung",
  "device_name": "Telefon"
}
```
Boshqa qatnashchilar ro'yxatida uning nomi *"Ali Valiyev (Telefon)"* ko'rinishida chiqadi.

---

## 11. Yig'ilishni Yakunlash (`close`)

Yig'ilishni mezbon tugatganda:
1. Mezbon REST so'rov yuboradi: `POST /api/meetings/{id}/close/`
2. Server LiveKit xonasini yopadi va barcha qatnashchilarga WebSocket orqali xabar yuboradi:
```json
{
  "type": "meeting_ended",
  "meeting_id": 16,
  "message": "Yig'ilish tugatildi."
}
```
3. Klient darhol LiveKit va WebSocket ulanishlarini yopadi va natija ekraniga o'tadi:
```typescript
await room.disconnect();
socket.close();
```

---

## 12. Davomat va Sabab Bildirish (`meeting-attendance`)

Davomat ro'yxatini olish: `GET /api/meeting-attendance/?meeting={meeting_id}`

### Qaytadigan yangi maydonlar:
```json
{
  "id": 29,
  "user_info": {
    "id": 3,
    "username": "ali",
    "position": "Dasturchi"
  },
  "meeting": 16,
  "meeting_title": "Haftalik tahlil",
  "meeting_start_time": "2026-09-23T10:00:00+05:00",
  "is_attended": true,
  "is_excused": false,
  "joined_at": "2026-09-23T10:08:00+05:00",
  "left_at": "2026-09-23T10:30:00+05:00",
  "duration_minutes": 22,
  "late_minutes": 8,
  "absence_reason": null,
  "reason_deadline": "2026-09-24T10:08:00+05:00",
  "can_submit_reason": true
}
```

* `can_submit_reason`: Agar `true` bo'lsa, xodim sabab yozish tugmasini bosib sabab kirita oladi.
* `reason_deadline`: Sabab kiritish mumkin bo'lgan oxirgi muddat (aniq 24 soat).
* **Sabab kiritish (Xodim):** `PATCH /api/meeting-attendance/{id}/` -> `{"absence_reason": "Kechikish sababi matni..."}`
* **Sababni baholash (Mezbon):** `PATCH /api/meeting-attendance/{id}/` -> `{"is_excused": true}` yoki `false`

---

## 13. Deep-Link va UID bo'yicha Yig'ilishni Topish

Web va Mobile'da `https://app.raqamlinazorat.uz/meetings/MT-0009` havolasi ochilganda:
* Backendga to'g'ridan-to'g'ri so'rov yuborish mumkin:
  `GET /api/meetings/?uid=MT-0009`
* Yoki umumiy qidiruv orqali:
  `GET /api/meetings/?search=MT-0009`

Ikkala holatda ham backend aniq o'sha yig'ilishni topib beradi.
