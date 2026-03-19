---
name: 备忘录skill
description: >
  Lightweight learning memo skill for OpenClaw. Supports:
  (1) daily memo logging by date,
  (2) one-time reminder (e.g. 1 hour later),
  (3) daily recurring reminder,
  (4) reminder scan for OpenClaw scheduled jobs,
  (5) Ebbinghaus review table grouped by review date.

  Trigger this skill when user says:
  - "我今天做了...", "记录...", "我今天学了..."
  - "今天我做了什么", "最近7天我学了什么"
  - "一小时后提醒我...", "每天9点提醒我..."
  - "查看艾宾浩斯复习表", "查看遗忘曲线提醒", "今天要复习什么"
---

# OpenClaw Memo Skill

Use this skill to store daily learning/work notes and run scheduled reminders.

## Intents

- `record`: add a dated memo.
- `query`: list memos by day range.
- `remind_once`: create one-time reminder from natural language time.
- `remind_daily`: create daily reminder from fixed local time.
- `scan_due`: return due reminders for OpenClaw to notify.
- `review_table`: build and return Ebbinghaus review table by date.

## Runtime Contract

- Preferred entrypoint for OpenClaw: `scripts/openclaw_adapter.ps1` with JSON request payload.
- OpenClaw conversation flow should call `ingest` or explicit commands.
- OpenClaw scheduler should call `scan-due` every minute.
- OpenClaw notification layer sends user-facing reminder text.
- OpenClaw can call `review-table` for tabular review content.
- Notification delivery should callback runtime:
  - success: `ack-reminder --id <id>`
  - failure: `fail-reminder --id <id> --error "..."`
