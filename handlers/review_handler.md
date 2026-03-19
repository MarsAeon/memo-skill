# Review Handler

## Goal
Provide Ebbinghaus review reminders in a date-based table and include all scheduled items across memo dates.

## Strategy
- Fixed intervals: `1, 2, 4, 7, 15, 30` days.
- Source of truth: `data/memos.jsonl`.
- Completion log: `data/review_log.jsonl`.
- Generated table rows: `data/review_table.json`.

## Output
1. Structured JSON rows grouped by `review_date`.
2. Markdown table with columns:
	- `复习日期`
	- `阶段`
	- `状态`
	- `记录日期`
	- `内容`

## Commands
- `review-table`: full table.
- `review-table --due-only`: today/overdue items only.
- `review-done --memo-id <id> --stage Rn`: mark a stage complete.
