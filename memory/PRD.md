# PaintOps Daily - PRD

## Overview
Field-ops daily reporting mobile app for a painting/construction company. Field managers, ops, and owners share AI-generated daily summaries with GPS visits, breaks, communications logs, weather context, voice-dictated notes, photos, customer signatures, weekly executive digest, live map pins, portal share links, push notifications, and voice narration.

## Stack
- Expo Router (React Native) frontend, iOS + Android + Web
- FastAPI + MongoDB backend, APScheduler for weekly cron
- Emergent Universal LLM Key (GPT 5.4 summaries + digests, Whisper-1 transcription)
- Emergent Resend for daily & weekly emails
- Emergent Managed Push (SuprSend passthrough)
- Emergent Managed Object Storage for visit photos
- ElevenLabs TTS for "Read aloud"
- Open-Meteo for weather
- react-native-maps native / chip fallback on web
- react-native-signature-canvas for customer sign-off

## Roles
Owner, Operations, Sales, Production, Labor (Subcontractor), Project Manager. Admin creates users. Owner/Ops/PM see all reports; others see only their own.

## Feature list
### Core
- Email/password auth (JWT) with role-based access
- Home hub: weather widget, quick actions, today's activity, today's reports, active-break banner, offline-queue banner
- Interaction Map: GPS check-in with customer info & project code, live pins, photo attachments (up to 3 per visit)
- Break tracker: Bathroom / Lunch / Personal / Admin Call
- Communications Log: SMS/Call/Email with category & direction
- Report Composer → GPT 5.4 AI summary + Resend email to management + voice-to-notes mic
- Report list: kebab menu → Edit / Share (native share sheet: email/SMS/etc) / Archive / Delete (soft)
- Report detail: AI summary + Workday CSV export + Customer signature pad + Portal share link (public URL, no auth) + **Read aloud (ElevenLabs TTS, cached per summary hash)**
- Admin: manage users (role/title/department/job code), customer directory, weekly digest (manual send + Monday-morning auto-scheduler)

### Cross-cutting
- **Push notifications** (Emergent managed): fires on report create (→ owner/ops/admin), digest send (→ management), signature captured (→ report author). Tap deep-links to `/report/{id}`.
- **Offline queue**: caches visits/breaks/sms during network drops; flushes on next Home load.
- **Portal share link**: `GET /api/public/reports/{token}` returns a limited public JSON view — no login required.

## Test credentials
See `/app/memory/test_credentials.md`.

## Deferred
- Real Workday API push (currently CSV export)
- Real SMS auto-scan (blocked by iOS/Android policies)
- Apple Sign-In (playbook loaded; requires iOS 26+ real device build)
- Nano Banana image generation for report covers
- Split server.py into routers (currently 1560 lines)
