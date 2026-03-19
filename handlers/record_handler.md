# Record Handler

## Goal
Convert natural language like `我今天做了...` into a dated memo and append to `data/memos.jsonl`.

## Rules
1. Strip common prefixes: `我今天做了`, `我今天学了`, `记录:`.
2. Empty content is invalid.
3. Same day + same normalized content is deduped.
4. Save `created_at` in ISO8601 with configured timezone.

## Output
- `created`: new memo inserted.
- `deduped`: existing memo returned.
