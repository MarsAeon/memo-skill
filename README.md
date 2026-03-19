# OpenClaw Learning Memo Skill (MVP)

A lightweight skill to track what you did/learned and run reminders.

## Features
- Dated memo logging from natural language.
- Query recent memos (default 7 days).
- One-time reminder (`X分钟后`, `X小时后`, `明天...`).
- Daily recurring reminder (`每天HH:mm提醒我...`).
- Due reminder scanner for OpenClaw scheduled jobs.
- Ebbinghaus review table by date (all review items across different memo dates).

## Structure
- `SKILL.md`: skill metadata and runtime contract.
- `src/memo_skill.py`: executable runtime.
- `src/openclaw_adapter.py`: unified JSON adapter for OpenClaw.
- `config/runtime.json`: timezone + scan config.
- `data/`: persisted memo/reminder files.
- `handlers/` and `templates/`: behavior and prompt docs.

## Runtime Commands
From workspace root:

```powershell
python .\src\memo_skill.py ingest --text "我今天做了接口联调"
python .\src\memo_skill.py query --days 7
python .\src\memo_skill.py add-once --expr "1小时后提醒我提交日报"
python .\src\memo_skill.py add-daily --time "09:00" --message "完成待办"
python .\src\memo_skill.py scan-due
python .\src\memo_skill.py ack-reminder --id "<reminder-id>"
python .\src\memo_skill.py fail-reminder --id "<reminder-id>" --error "push failed"
python .\src\memo_skill.py review-table
python .\src\memo_skill.py review-table --due-only
python .\src\memo_skill.py review-done --memo-id "<memo-id>" --stage "R1"
python .\src\memo_skill.py normalize-timezones
```

## Ebbinghaus Review Table
- Intervals: `1, 2, 4, 7, 15, 30` days.
- Runtime generates a date-based table for all memos and stores raw rows to `data/review_table.json`.
- Query phrases like `查看艾宾浩斯复习表` or `查看遗忘曲线提醒` can route via `ingest`.
- Each row includes: review date, stage, status, memo date, content.

## OpenClaw Integration
### Recommended: Unified JSON Adapter
Use a single command entrypoint so OpenClaw only needs one integration:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\openclaw_adapter.ps1 '{"action":"ingest","text":"我今天做了接口联调"}'
```

Supported `action` values:
- `health`
- `ingest`
- `query`
- `add_once`
- `add_daily`
- `scan_due`
- `ack`
- `fail`
- `cancel`
- `review_table`
- `review_done`
- `normalize_timezones`

Example scheduler payload:

```json
{"action":"scan_due"}
```

Example callback payloads:

```json
{"action":"ack","id":"<reminder-id>"}
{"action":"fail","id":"<reminder-id>","error":"push failed"}
```

### Direct CLI (Alternative)
1. Conversation stage:
- Call `ingest --text "<user input>"`.

2. Scheduler stage:
- Configure OpenClaw timed job every 60s.
- Timed job runs: `python .\src\memo_skill.py scan-due`.
- For each returned `due` reminder, OpenClaw sends notification.
- If send succeeds, call `ack-reminder --id <id>`.
- If send fails, call `fail-reminder --id <id> --error "..."`.

3. Delivery retry policy:
- Reminder enters `PENDING_NOTIFY` after `scan-due` claim.
- `fail-reminder` schedules retry with `next_retry` (default 60s).
- After max attempts (`max_delivery_attempts`), status becomes `FAILED`.

4. Cancel reminder:
- Call `python .\src\memo_skill.py cancel --id <reminder_id>`.

## Production Rollout Checklist
1. Use `config/runtime.prod.json` values in production.
2. Run `normalize-timezones` once before first production schedule.
3. Configure OpenClaw job to execute `scripts/openclaw_scan.ps1` every 60 seconds.
4. Ensure OpenClaw notification worker executes ACK/FAIL callbacks.
5. Monitor `FAILED` reminders and retry manually if needed.

## Notes
- Timezone comes from `config/runtime.json` (`Asia/Shanghai` default).
- Dedup rules:
  - Memo: same day + same normalized content.
  - Reminder: same type + same message + same trigger.
- Ebbinghaus review is Phase 2 and intentionally not enabled in MVP.
