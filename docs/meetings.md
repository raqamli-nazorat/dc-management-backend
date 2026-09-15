# LiveKit Video Konferensiya va WebSocket Integratsiya Qo'llanmasi (Frontend uchun)

Ushbu qo'llanma **LiveKit** va **Django Channels (WebSocket)** orqali video yig'ilishlarni frontendda (React, Vue, Angular yoki mobil ilovalar) noldan to'liq integratsiya qilish uchun mo'ljallangan.

---

## 1. Umumiy Arxitektura va Ishlash Tartibi

Tizim uchta asosiy qismdan iborat:
1. **Django REST API**: Yig'ilishlarni boshqarish (yaratish, tahrirlash, yakunlash, davomatni ko'rish).
2. **Django WebSocket (`/api/ws/meetings/<meeting_id>/`)**: Kirish ruxsatlari, kutish xonasi (Waiting room), mezbon tasdig'i (Knock & Admit), avtomatik token uzatish va yig'ilish holatlarini sinxronlash.
3. **LiveKit WebRTC Server**: Yuqori sifatli audio, video, ekran ulashish va real-vaqt ma'lumotlari (chat/raise hand).

---

## 2. WebSocket Ulanishlarning Farqi va Hayot Sikli (Lifecycle)

Loyiha ikkita mutlaqo boshqa WebSocket kanalidan foydalanadi:

### A. Global Bildirishnomalar WebSocket'i (`/api/ws/notifications/`)
* **Qachon ulanadi?** Foydalanuvchi saytga/ilovaga kirishi (login bo'lishi) bilanoq 1 marta ulanadi.
* **Qachongacha ochiq turadi?** Butun dastur bo'yicha orqa fonda (global) doimiy ochiq turadi.
* **Vazifasi:** Yangi vazifalar, tizim bildirishnomalari va `"meeting_started"` (Yig'ilish boshlandi, agar foydalanuvchi hali kirmagan bo'lsa) kabi xabarlarni qabul qilish.

### B. Yig'ilish WebSocket'i (`/api/ws/meetings/<meeting_id>/`)
* **Qachon ulanadi?** FAQAT foydalanuvchi muayyan yig'ilish sahifasiga kirganida (yoki "Yig'ilishga kirish" tugmasini bosganida).
* **Qachon uziladi (`disconnect`)?** Foydalanuvchi yig'ilish sahifasidan chiqqanda (komponent unmount bo'lganda) yoki yig'ilish tugaganda (`meeting_ended` hodisasi kelganda).
* **Vazifasi:** Yig'ilish xonasining kutish zali, daxlsizlik tekshiruvi, mezbon tasdig'i (knock & admit), LiveKit tokenini qabul qilish va xonadagi jonli holatlarni boshqarish.

> [!WARNING]
> **Muhim:** `/api/ws/meetings/<meeting_id>/` ga sayt ochilishi bilan global ulab qo'ymang! Unda muayyan `meeting_id` bo'lishi shart va u faqat foydalanuvchi yig'ilish oynasida o'tirgan paytidagina faol bo'lishi kerak. Yig'ilish tugashi bilan `ws.close()` qilinishi shart!

---

## 3. Autentifikatsiya (Ticket tizimi)

WebSocket ulanishlari xavfsiz bir martalik bilet (**Ticket**) orqali amalga oshiriladi:

### 1-qadam: Ticket olish (REST API)
* **URL:** `POST /api/notifications/tickets/`
* **Headers:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
* **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "ticket": "9b1deb4d-3b7d-4bad-9bdd-2b0d7b3dcb6d",
    "expires_in": 60
  }
}
```

### 2-qadam: WebSocket'ga ulanish
Olingan ticket bilan WebSocket ulanishini oching:
```
wss://<domain>/api/ws/meetings/<meeting_id>/?ticket=<ticket>
```
*(Lokal muhitda: `ws://127.0.0.1:8000/api/ws/meetings/16/?ticket=...`)*  
*(Production muhitida: `wss://backend.raqamlinazorat.uz/api/ws/meetings/16/?ticket=...`)*

---

## 4. Xavfsizlik, Daxlsizlik va Xatoliklarni Qayta Ishlash

Agar foydalanuvchi yig'ilishga kirish huquqiga ega bo'lmasa, server ulanishni yopishdan oldin **aniq JSON xatolik hodisasi** yuboradi va shundan so'ng ulanishni yopadi:

### A. Ruxsat yo'q (403 Forbidden):
Yig'ilishga **faqat tashkilotchi va taklif qilingan qatnashchilar** kira oladi. Agar foydalanuvchi (shu jumladan tizim admini yoki loyiha menejeri ham) ushbu yig'ilish qatnashchilar ro'yxatida bo'lmasa, yig'ilish daxlsiz hisoblanadi va xonaga kiritilmaydi:
```json
{
  "type": "error",
  "code": 403,
  "message": "Siz ushbu yig'ilish qatnashchisi emassiz."
}
```
*WebSocket yopilish kodi:* `4003`

### B. Yig'ilish topilmadi yoki allaqachon tugagan (404 Not Found):
Tugagan yig'ilishlarga qayta kirish taqiqlangan:
```json
{
  "type": "error",
  "code": 404,
  "message": "Ushbu yig'ilish allaqachon tugagan yoki mavjud emas."
}
```
*WebSocket yopilish kodi:* `4004`

### C. Login qilinmagan (401 Unauthorized):
Ticket yaroqsiz yoki berilmagan bo'lsa:
```json
{
  "type": "error",
  "code": 401,
  "message": "Autentifikatsiyadan o'tilmagan."
}
```
*WebSocket yopilish kodi:* `4003`

### Frontendda xatoliklarni tutib olish namunasi:
```javascript
socket.onmessage = (event) => {
  const data = JSON.parse(event.data);

  if (data.type === 'error') {
    toast.error(data.message); // Masalan: "Siz ushbu yig'ilish qatnashchisi emassiz."
    return;
  }
  // ... boshqa hodisalar
};

socket.onclose = (event) => {
  if (event.code === 4003) {
    console.warn("Kirish taqiqlandi (403)");
  } else if (event.code === 4004) {
    console.warn("Yig'ilish tugagan yoki mavjud emas (404)");
  }
};
```

---

## 5. Ulanish va Boshlang'ich Holat (`meeting_state`)

Foydalanuvchi muvaffaqiyatli ulanganda, server avtomatik ravishda yig'ilishning joriy holatini qaytaradi:

```json
{
  "type": "meeting_state",
  "meeting_id": 16,
  "title": "Haftalik loyiha tahlili",
  "requires_approval": true,
  "organizer_joined": true,
  "is_host": true,
  "is_approved": true,
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "server_url": "wss://locale.alijonov.uz",
  "room_name": "MT0009"
}
```

### Parametrlar tavsifi:
| Maydon | Tip | Tavsif |
| :--- | :--- | :--- |
| `meeting_id` | `int` | Yig'ilish identifikatori |
| `title` | `string` | Yig'ilish nomi |
| `requires_approval` | `bool` | Mezbon tasdig'i talab qilinadimi? |
| `organizer_joined` | `bool` | Tashkilotchi (mezbon) yig'ilishga kirganmi? |
| `is_host` | `bool` | **Mezbon (Host / Co-host) vakolati:** Agar foydalanuvchi tashkilotchi bo'lsa, YOKI ushbu yig'ilishga qatnashchi sifatida qo'shilgan Admin/Loyiha menejeri bo'lsa `true` bo'ladi. Ular qatnashchilarni qabul qila oladi va yig'ilishni boshqara oladi. |
| `is_approved` | `bool` | Ushbu foydalanuvchiga kirishga ruxsat berilganmi? |
| `token` | `string \| null` | LiveKit WebRTC xonasiga kirish tokeni (ruxsat bo'lsa darhol keladi) |
| `server_url` | `string \| null` | LiveKit server manzili |
| `room_name` | `string \| null` | LiveKit xonasi nomi (`meeting.uid`) |

---

## 6. Kutish Xonasi Mantiqi (Waiting Room Flow)

Foydalanuvchi mezbon bo'lmasa (`is_host: false`), kirish tartibi quyidagicha kechadi:

### 1-bosqich: Mezbon kirmagan (`organizer_joined: false`)
* Frontend ekranda kutish xabarnomasini ko'rsatadi: *"Tashkilotchi yig'ilishga kirmaguncha kuting..."*
* Serverdan quyidagi hodisa keladi:
```json
{
  "type": "waiting_organizer",
  "message": "Tashkilotchi yig'ilishga kirmaguncha kuting."
}
```
* **Frontend hech qanday polling qilishi shart emas!**
* Tashkilotchi kirishi bilan server barcha kutib turganlarga `organizer_joined` hodisasini yuboradi:
```json
{
  "type": "organizer_joined",
  "meeting_id": 16,
  "message": "Tashkilotchi yig'ilishga kirdi."
}
```
> [!NOTE]
> Agar yig'ilishda tasdiqlash talab qilinmasa (`requires_approval: false`), tashkilotchi kirishi bilan kutib turganlarga avtomatik ravishda `token_response` (token bilan) keladi va ular sahifani yangilamasdan to'g'ridan-to'g'ri xonaga kirib ketadi!

---

## 7. Mezbon Tasdig'i (Google Meet uslubidagi "Knock & Admit")

Agar yig'ilishda `requires_approval: true` bo'lsa va foydalanuvchi hali tasdiqlanmagan bo'lsa (`is_approved: false`):

### 1-qadam: Xodim kirishni so'raydi (Knock)
Frontend WebSocket orqali quyidagi so'rovni yuboradi:
```json
{
  "action": "ask_to_join"
}
```
Frontend ekranda: *"Mezbon tasdiqlashini kuting..."* ko'rsatiladi.

### 2-qadam: Mezbonlar ekraniga so'rov kelishi (Host & Co-host)
Tashkilotchi hamda qatnashchi bo'lgan Admin/Menejerlarning ekranida `knock_request` xabari chiqadi:
```json
{
  "type": "knock_request",
  "meeting_id": 16,
  "user_id": 45,
  "username": "Ali Valiyev",
  "avatar": "/media/avatars/ali.jpg"
}
```
Frontend mezbonlar ekranida "Qabul qilish" (Admit) va "Rad etish" (Reject) tugmalari bilan modal/popup ko'rsatadi.

### 3-qadam: Mezbon qaror qabul qiladi
Mezbon WebSocket orqali quyidagi JSON'ni yuboradi:
```json
{
  "action": "admit",
  "user_id": 45,
  "decision": "approve" 
}
```
*(Rad etish uchun: `"decision": "reject"`)*

### 4-qadam: Xodim natijani qabul qiladi (`knock_response`)

#### Agar tasdiqlansa (`status: "approved"`):
```json
{
  "type": "knock_response",
  "status": "approved",
  "server_url": "wss://locale.alijonov.uz",
  "room_name": "MT0009",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```
Frontend ushbu `token` va `server_url` orqali to'g'ridan-to'g'ri LiveKit xonasiga ulanadi.

#### Agar rad etilsa (`status: "rejected"`):
```json
{
  "type": "knock_response",
  "status": "rejected",
  "message": "Mezbon yig'ilishga kirishingizni rad etdi."
}
```

---

## 8. LiveKit Tokenini Olish (`get_token`)

Agar foydalanuvchi tasdiqlangan bo'lsa yoki tasdiq talab etilmasa, istalgan paytda tokenni qayta so'rash mumkin:
```json
{
  "action": "get_token"
}
```
**Server javobi:**
```json
{
  "type": "token_response",
  "status": "joined",
  "server_url": "wss://locale.alijonov.uz",
  "room_name": "MT0009",
  "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9..."
}
```

---

## 9. LiveKit SDK bilan Ulanish (Frontend JS/TS Kodi)

### 1-qadam: Kutubxonani o'rnatish
```bash
npm install livekit-client
```

### 2-qadam: Xonaga ulanish kodi
```typescript
import { Room, RoomEvent, VideoPresets } from 'livekit-client';

const room = new Room({
  adaptiveStream: true,
  dynacast: true,
  videoCaptureDefaults: {
    resolution: VideoPresets.h720.resolution,
    simulcast: true,
  },
  publishDefaults: {
    simulcast: true,
    videoSimulcastLayers: [
      VideoPresets.h1080,
      VideoPresets.h720,
      VideoPresets.h360
    ]
  }
});

async function joinConference(serverUrl: string, token: string) {
  // 1. LiveKit xonasiga ulanish
  await room.connect(serverUrl, token);
  console.log("Xonaga muvaffaqiyatli ulandi:", room.name);

  // 2. O'z kamera va mikrofonini yoqish
  await room.localParticipant.enableCameraAndMicrophone();

  // O'z videomizni ekranda ko'rsatish
  const localVideoTrack = room.localParticipant.getTrackPublication('camera')?.videoTrack;
  if (localVideoTrack) {
    const element = localVideoTrack.attach();
    document.getElementById('local-video-container')?.appendChild(element);
  }

  // 3. Boshqa ishtirokchilar kamerasi/ovozini qabul qilish
  room.on(RoomEvent.TrackSubscribed, (track, publication, participant) => {
    const element = track.attach();
    const container = document.getElementById(`participant-${participant.identity}`);
    if (container) {
      container.appendChild(element);
    }
  });

  // 4. Ishtirokchi chiqqanda uning elementlarini tozalash
  room.on(RoomEvent.TrackUnsubscribed, (track) => {
    track.detach();
  });
}
```

### 3-qadam: Mikrofon / Kamera / Ekran boshqaruvi
```typescript
async function toggleMic(enabled: boolean) {
  await room.localParticipant.setMicrophoneEnabled(enabled);
}

async function toggleCamera(enabled: boolean) {
  await room.localParticipant.setCameraEnabled(enabled);
}

async function toggleScreenShare(enabled: boolean) {
  await room.localParticipant.setScreenShareEnabled(enabled);
}

async function leaveRoom() {
  await room.disconnect();
}
```

### 4-qadam: Jonli Chat va Reaksiyalar (WebRTC Data Channel)
Tokenlar `can_publish_data: true` bilan beriladi. LiveKit orqali 0 ms kechikish bilan xabar almashish mumkin:

```typescript
// 1. Chat xabari yuborish
async function sendChatMessage(text: string, currentUserName: string) {
  const messageData = {
    type: 'chat',
    text: text,
    sender: currentUserName,
    time: new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
  };
  const payload = new TextEncoder().encode(JSON.stringify(messageData));
  await room.localParticipant.publishData(payload, { reliable: true });
}

// 2. Xabarlarni qabul qilish
room.on(RoomEvent.DataReceived, (payload: Uint8Array, participant) => {
  const decoded = JSON.parse(new TextDecoder().decode(payload));
  if (decoded.type === 'chat') {
    console.log(`${decoded.sender}: ${decoded.text}`);
  }
});
```

---

## 10. Yig'ilishni Yakunlash (`close`)

Yig'ilishni tashkilotchi, qatnashchi bo'lgan admin yoki menejer tugatishi mumkin:
1. **REST API so'rovi:**
   * **URL:** `POST /api/meetings/<meeting_id>/close/`
   * **Headers:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
2. **Natija:**
   * LiveKit Media Serveri xonani o'chiradi va ichidagi barcha ishtirokchilarni uzib yuboradi.
   * Xonadagi barcha foydalanuvchilarga `meeting_ended` hodisasi boradi:
```json
{
  "type": "meeting_ended",
  "meeting_id": 16,
  "message": "Yig'ilish tugatildi."
}
```
3. **Frontend nima qilishi kerak:**
   ```typescript
   await room.disconnect();
   meetingWs.close();
   showModal("Yig'ilish mezbon tomonidan yakunlandi");
   ```

---

## 11. Yig'ilish Davomatini Olish (`meeting-attendance`)

Yig'ilish tugaganidan keyin yoki davomida qatnashuvchilar davomatini olish uchun:
* **URL:** `GET /api/meeting-attendance/?meeting=<meeting_id>`
* **Headers:** `Authorization: Bearer <JWT_ACCESS_TOKEN>`
* **Response (200 OK):**
```json
{
  "success": true,
  "data": {
    "count": 2,
    "results": [
      {
        "id": 29,
        "user_info": {
          "id": 3,
          "username": "Alijonov Abdulbosit",
          "position": "Dasturchi"
        },
        "meeting": 16,
        "meeting_title": "Haftalik loyiha tahlili",
        "is_attended": true,
        "is_excused": false,
        "joined_at": "2026-09-13T10:00:00+05:00",
        "left_at": "2026-09-13T10:30:00+05:00",
        "duration_minutes": 30,
        "late_minutes": 8,
        "absence_reason": null
      }
    ]
  }
}
```

### Davomat va Sabab Kiritish Qoidalari:
> [!NOTE]
> **Adolatli kechikish hisobi:** Kechikish daqiqasi `max(meeting.start_time, organizer_joined_at)` (rejalashtirilgan vaqt yoki tashkilotchi kirgan vaqtning kattasi)ga nisbatan o'lchanadi. Agar tashkilotchi yig'ilishga kechikib kirsa, qatnashchilar uchun boshlanish vaqti tashkilotchi kirgan paytdan hisoblanadi (xodimlar asossiz kechikkan hisoblanmaydi).

1. **O'z vaqtida kirganlar (`is_attended: true` va `late_minutes <= 5`)**:
   - Jarima yo'q (0%), sabab kiritish talab etilmaydi.
2. **Kechikib kirganlar (`is_attended: true` va `late_minutes > 5`)**:
   - Foydalanuvchiga kechikkanligi haqida bildirishnoma boradi.
   - Foydalanuvchi kirgan paytidan boshlab **24 soat ichida** `PATCH /api/meeting-attendance/<id>/` orqali `absence_reason` (kechikish sababi) yuborishi mumkin. 24 soat o'tgach, sabab qabul qilinmaydi.
3. **Umuman kirmaganlar (`is_attended: false`)**:
   - Yig'ilish tugagach, qatnashmaganligi haqida bildirishnoma boradi.
   - Foydalanuvchi **24 soat ichida** `PATCH /api/meeting-attendance/<id>/` orqali `absence_reason` (qatnashmaslik sababi) yuborishi mumkin.
4. **Tashkilotchi / Mas'ul tomonidan ko'rib chiqish**:
   - Tashkilotchi yoki loyiha menejeri `PATCH /api/meeting-attendance/<id>/` orqali `{"is_excused": true}` (sababli) yoki `{"is_excused": false}` (sababsiz) deb baholaydi.
   - Natija bo'yicha xodimga bildirishnoma yetkaziladi.

### Jarimalar Shkalasi:
* **Agar `is_excused: true` bo'lsa**: 0% (jarima hisoblanmaydi).
* **Agar `is_excused: false` bo'lsa (yoki 24 soat ichida sabab kiritilmasa)**:
  - `0 <= late_minutes <= 5`: **0%** (ruxsat etilgan norma, jarimasiz)
  - `5 < late_minutes <= 15`: **0.1%** oylikdan
  - `15 < late_minutes <= 25`: **0.5%** oylikdan
  - `late_minutes > 25`: **1.0%** oylikdan
  - Umuman kirmagan bo'lsa (`is_attended: false`): **yig'ilishga belgilangan foiz** (`penalty_percentage`)

---

## 12. Frontend uchun To'liq State Mashinasi

```
[Boshlanish]
    │
    ▼
1. POST /api/notifications/tickets/ ──► Ticket olish
    │
    ▼
2. wss://.../api/ws/meetings/<id>/?ticket=... ga ulanish
    │
    ├─► type == "error" (code: 403 / 404 / 401) ──► Toast xato va oynadan chiqish
    │
    ▼
3. "meeting_state" xabarini kutib olish
    │
    ├─► is_host == true (Tashkilotchi yoki Hamkor Admin/Menejer)
    │       │
    │       ▼
    │   Token bilan LiveKit'ga kirish va Kutish zalini boshqarish (admit)
    │
    └─► is_host == false (Oddiy qatnashchi)
            │
            ├─► organizer_joined == false ──► "Mezbon kirishini kuting" ekrani
            │       │
            │       └─► "organizer_joined" kelganda ──┐
            │                                         │
            └─► organizer_joined == true  ◄───────────┘
                    │
                    ├─► requires_approval == true va is_approved == false
                    │       │
                    │       ├─► {"action": "ask_to_join"} yuborish
                    │       │
                    │       ├─► "knock_response" (status: approved) ──► LiveKit'ga kirish
                    │       │
                    │       └─► "knock_response" (status: rejected) ──► "Rad etildi"
                    │
                    └─► requires_approval == false yoki is_approved == true
                            │
                            ▼
                        LiveKit'ga kirish (token_response orqali)
```
