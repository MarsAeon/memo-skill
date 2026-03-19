# Query Handler

## Goal
Return memo history for a day window.

## Rules
1. Default range is recent 7 days.
2. Sort by `created_at` desc.
3. User-facing response should include date and content.

## Typical Inputs
- `今天我做了什么`
- `最近7天我学了什么`
