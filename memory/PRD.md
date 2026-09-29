# PaintOps Daily - PRD

## Overview
Daily reporting mobile app for a painting/construction company. Field managers, ops, and owners share AI-generated daily summaries with GPS visits, breaks, communications logs, and weather context.

## Stack
- Expo Router (React Native) frontend, iOS + Android + Web
- FastAPI + MongoDB backend
- Emergent Universal LLM Key for GPT 5.4 summaries
- Emergent Resend for email digest
- Open-Meteo for weather (no API key)

## Roles
Owner, Operations, Sales, Production, Labor (Subcontractor), Project Manager.
Admin can create users. Owner/Ops/PM see all reports; others see only their own.

## Features (MVP)
- Email/password auth (JWT) with role-based access
- Home hub: weather widget (GPS), quick actions (Start Day / Add Break / End Day), today's activity
- Interaction Map: GPS-tagged customer visits with notes and project code, end visit
- Break tracker: Bathroom / Lunch / Personal / Admin Call with reasons + call details block
- Communications Log: manual entry of SMS/Call/Email with category, direction, content
- Report Composer: pulls today's visits/breaks/sms/weather + manual highlights/delays/change orders → GPT 5.4 AI summary → emails to management via Resend
- Report detail: AI summary + all embedded sections + Workday CSV export
- Admin: create users with role/title/dept/job code

## Integrations
- Emergent LLM Key (GPT 5.4) for AI summary
- Emergent Resend for email digest
- Open-Meteo for weather
- expo-location for GPS

## Deferred (Post-MVP)
- Native react-native-maps
- Apple Sign-In (playbook loaded; requires iOS 26+ device build)
- Nano Banana image generation for report covers
- Real Workday API push (currently CSV export)
- Real SMS auto-scan (blocked by iOS/Android policies)
