import argparse
import json
import traceback
from typing import Any, Dict

import memo_skill


def _require(payload: Dict[str, Any], field: str) -> Any:
    if field not in payload:
        raise ValueError(f"missing required field: {field}")
    return payload[field]


def handle_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    action = payload.get("action")
    if not action:
        raise ValueError("missing required field: action")

    if action == "health":
        return {"status": "ok", "service": "memo-skill-adapter"}

    if action == "ingest":
        return memo_skill.ingest(_require(payload, "text"))

    if action == "query":
        days = int(payload.get("days", 7))
        return {"status": "ok", "result": memo_skill.query_memos(days=days)}

    if action == "add_once":
        return memo_skill.add_once_reminder(_require(payload, "expr"))

    if action == "add_daily":
        return memo_skill.add_daily_reminder(
            str(_require(payload, "time")),
            str(_require(payload, "message")),
        )

    if action == "scan_due":
        return memo_skill.scan_due()

    if action == "ack":
        return memo_skill.ack_reminder(str(_require(payload, "id")))

    if action == "fail":
        return memo_skill.fail_reminder(
            str(_require(payload, "id")),
            str(payload.get("error", "delivery failed")),
        )

    if action == "cancel":
        return memo_skill.cancel_reminder(str(_require(payload, "id")))

    if action == "review_table":
        return memo_skill.get_review_table(
            from_date=payload.get("from_date") or None,
            to_date=payload.get("to_date") or None,
            due_only=bool(payload.get("due_only", False)),
        )

    if action == "review_done":
        return memo_skill.mark_review_done(
            str(_require(payload, "memo_id")),
            str(_require(payload, "stage")),
        )

    if action == "normalize_timezones":
        return memo_skill.normalize_timezones()

    raise ValueError(f"unknown action: {action}")


def main() -> None:
    memo_skill._ensure_data_files()

    parser = argparse.ArgumentParser(description="OpenClaw JSON adapter for memo skill")
    parser.add_argument("--request", default="", help="JSON request string")
    args = parser.parse_args()

    try:
        raw = args.request.strip() if args.request else ""
        if raw:
            payload = json.loads(raw)
        else:
            stdin_text = input().strip()
            payload = json.loads(stdin_text)

        result = handle_request(payload)
        print(json.dumps({"ok": True, "data": result}, ensure_ascii=False, indent=2))
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": str(exc),
                    "trace": traceback.format_exc(limit=2),
                },
                ensure_ascii=False,
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
