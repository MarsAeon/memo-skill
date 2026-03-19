# Reminder Handler

## Goal
Support one-time and daily recurring reminders.

## One-time (ONCE)
- Parse text such as `30分钟后提醒我喝水`, `1小时后提醒我写日报`, `明天下午3点提醒我开会`.
- Create `type=ONCE` reminder.
- At fire time, update status to `FIRED`.

## Daily (DAILY)
- Parse text like `每天9点提醒我完成待办`.
- Create `type=DAILY` reminder.
- On every fire, roll `next_fire` to next day same local clock time.

## Scan Contract
`scan-due` returns due reminders for OpenClaw to deliver, then updates reminder state.

## Failure Policy
If downstream notify fails, caller may retry once and then fallback to in-session notice.
