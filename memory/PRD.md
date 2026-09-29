# PaintOps Daily - PRD

## Overview
Daily reporting mobile app for a painting/construction company. Field managers, ops, and owners share AI-generated daily summaries with GPS visits, breaks, communications logs, weather, voice-dictated notes, customer directory, weekly executive digest, live map pins, and customer signature capture.

## Stack
- Expo Router (React Native) frontend, iOS + Android + Web
- FastAPI + MongoDB backend
- Emergent Universal LLM Key (GPT 5.4 summaries + digests, Whisper-1 transcription)
- Emergent Resend for daily & weekly emails
- Open-Meteo for weather
- react-native-maps for pins on native; chip fallback on web

## Roles
Owner, Operations, Sales, Production, Labor (Subcontractor), Project Manager.
Admin creates users. Owner/Ops/PM see all reports; others see only their own.

## Features
### Core (v1)
- Email/password auth (JWT) with role-based access
- Home hub: weather widget, quick actions, today's activity, active-break banner
- Interaction Map: GPS check-in with customer info & project code
- Break tracker: Bathroom / Lunch / Personal / Admin Call
- Communications Log: SMS/Call/Email with category & direction
- Report Composer → GPT 5.4 AI summary + Resend email to management
- Report detail + Workday CSV export
- Admin: create users with role/title/department/job code

### v2 additions
- **Voice-to-Notes**: mic button on Report composer (expo-audio → /api/transcribe → Whisper-1)
- **Customer Directory**: /api/customers CRUD + Map pick-from-list
- **Weekly Digest**: /api/digest/weekly (admin) rolls last 7 days → GPT 5.4 executive summary → email
- **Live Map Pins**: react-native-maps with color-coded markers (active=orange, done=green)
- **Signature Capture**: react-native-signature-canvas → PATCH /api/reports/{id}/signature (base64 PNG stored)

## Deferred (Post-v2)
- Real Workday API push (currently CSV export)
- Real SMS auto-scan (blocked by iOS/Android policies)
- Apple Sign-In (playbook loaded; requires iOS 26+ real device build)
- Nano Banana image generation for report covers

## Test credentials
See `/app/memory/test_credentials.md`.
