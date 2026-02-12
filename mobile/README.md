# Niv AI Mobile App

Native mobile app for Niv AI — chat with your ERPNext using AI, from your phone.

## Features
- 🔗 Pairing code system — connect to any ERPNext server
- 💬 Real-time streaming chat with SSE
- 🔧 Tool call indicators (see what AI is doing)
- 🌙 Dark theme (matches web UI)
- 💾 Persistent auth (auto-reconnect)
- 📱 Native Android/iOS experience

## Quick Start

### 1. Install Dependencies
```bash
cd mobile
npm install
```

### 2. Run in Development
```bash
npx expo start
# Scan QR code with Expo Go app on your phone
```

### 3. Build APK (Android)
```bash
# Install EAS CLI
npm install -g eas-cli
eas login

# Build preview APK
eas build -p android --profile preview

# Download APK from the build URL
```

### 4. Build without EAS (local)
```bash
npx expo prebuild
cd android
./gradlew assembleRelease
# APK at: android/app/build/outputs/apk/release/
```

## Server Setup

### Generate Pairing Code (Admin)
1. Go to ERPNext → Niv Settings → 📱 Mobile App
2. Set your Site URL (public URL or ngrok)
3. Call API:
```
POST /api/method/niv_ai.niv_core.api.mobile.generate_pairing_code
{"user_email": "user@company.com"}
```
4. Share the code with the user

### Connect from App
1. Open Niv AI app
2. Enter server URL
3. Enter pairing code
4. Done! Start chatting

## Architecture
```
Mobile App ←→ Frappe API (stream_chat SSE)
     ↓
Pairing Code → API Key + Secret → Auth Token
     ↓
Same agent, same tools, same responses as web chat
```
