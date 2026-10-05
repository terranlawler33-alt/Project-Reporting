# PaintOps Daily - PRD

## Overview
Field-ops daily reporting mobile app for a painting/construction company. Field managers, ops, and owners share AI-generated daily summaries with GPS visits, breaks, communications logs, weather context, voice-dictated notes, photos, customer signatures, weekly executive digest, live map pins, portal share links, push notifications, and voice narration.

## Stack
- Expo Router (React Native) frontend, iOS + Android + Web
- FastAPI + MongoDB backend, APScheduler for weekly cron
- Emergent Universal LLM Key (GPT 5.4 summaries + digests, Whisper-1 transcription, OpenAI TTS fallback)
- Emergent Resend for daily & weekly emails
- Emergent Managed Object Storage for visit photos
- ElevenLabs TTS for "Read aloud" (primary) with Emergent OpenAI TTS auto-fallback when quota exhausted
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
- **Offline queue**: caches visits/breaks/sms during network drops; flushes on next Home load.
- **Portal share link**: `GET /api/public/reports/{token}` returns a full **HTML** page with per-flagged-job "Respond" buttons and a general reply option; no login required.
- **Mail inbox**: dedicated Mail tab receives recipient replies with unread badge, read/archive/delete actions, deep-link into the related report.
- **Draft reports**: one rolling draft per day — auto-saves silently as the user edits; "Submit" finalizes it (AI summary + email). Resume banner on reports list.
- **Android SMS import**: Android-only "Import from phone" (READ_SMS, needs native build); iOS shows greyed button with Apple-restriction note.
- **Per-project Job Overview**: short summary attached to each project; shown on map pin tooltips, visit detail modal, and the public portal so the owner has a "virtual layout" of each sold job.

## Test credentials
See `/app/memory/test_credentials.md`.

## Deferred
- Real Workday API push (currently CSV export)
- Real SMS auto-scan (blocked by iOS/Android policies)
- Apple Sign-In (playbook loaded; requires iOS 26+ real device build)
- Nano Banana image generation for report covers
- Split server.py into routers (currently 1560 lines)
