import argparse
import json
import os
import re
import tempfile
import time
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None


ROOT = Path(__file__).resolve().parents[1]
RUNTIME_PATH = ROOT / "config" / "runtime.json"
MEMOS_PATH = ROOT / "data" / "memos.jsonl"
REMINDERS_PATH = ROOT / "data" / "reminders.json"
TODOS_PATH = ROOT / "data" / "todos.json"
REVIEW_LOG_PATH = ROOT / "data" / "review_log.jsonl"
REVIEW_TABLE_PATH = ROOT / "data" / "review_table.json"

REVIEW_INTERVAL_DAYS = [1, 2, 4, 7, 15, 30]


@dataclass
class RuntimeConfig:
    timezone_name: str
    scan_interval_seconds: int
    max_scan_batch: int
    retry_delay_seconds: int
    max_delivery_attempts: int


def _read_runtime() -> RuntimeConfig:
    payload = json.loads(RUNTIME_PATH.read_text(encoding="utf-8"))
    return RuntimeConfig(
        timezone_name=payload.get("timezone", "Asia/Shanghai"),
        scan_interval_seconds=int(payload.get("scan_interval_seconds", 60)),
        max_scan_batch=int(payload.get("max_scan_batch", 100)),
        retry_delay_seconds=int(payload.get("retry_delay_seconds", 60)),
        max_delivery_attempts=int(payload.get("max_delivery_attempts", 3)),
    )


def _tz(config: RuntimeConfig):
    # Windows Python may miss IANA tz database; keep a deterministic fallback.
    if config.timezone_name in ("Asia/Shanghai", "PRC", "China Standard Time"):
        return timezone(timedelta(hours=8))
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(config.timezone_name)
    except Exception:
        return timezone.utc


def _now_local(config: RuntimeConfig) -> datetime:
    return datetime.now(_tz(config))


def _lock_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".lock")


@contextmanager
def _file_lock(path: Path, timeout_seconds: float = 5.0):
    lock = _lock_path(path)
    start = time.time()
    fd = None
    while True:
        try:
            fd = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_RDWR)
            break
        except FileExistsError:
            if time.time() - start > timeout_seconds:
                raise TimeoutError(f"lock timeout for {path}")
            time.sleep(0.05)

    try:
        yield
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock.unlink(missing_ok=True)
        except Exception:
            pass


def _ensure_data_files() -> None:
    MEMOS_PATH.parent.mkdir(parents=True, exist_ok=True)
    if not MEMOS_PATH.exists():
        MEMOS_PATH.write_text("", encoding="utf-8")
    if not REMINDERS_PATH.exists():
        REMINDERS_PATH.write_text("[]\n", encoding="utf-8")
    if not TODOS_PATH.exists():
        TODOS_PATH.write_text("[]\n", encoding="utf-8")
    if not REVIEW_LOG_PATH.exists():
        REVIEW_LOG_PATH.write_text("", encoding="utf-8")
    if not REVIEW_TABLE_PATH.exists():
        REVIEW_TABLE_PATH.write_text("[]\n", encoding="utf-8")


def _read_json_array(path: Path) -> List[Dict[str, Any]]:
    try:
        return json.loads(path.read_text(encoding="utf-8") or "[]")
    except json.JSONDecodeError:
        return []


def _write_json_array(path: Path, payload: List[Dict[str, Any]]) -> None:
    with _file_lock(path):
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", delete=False, dir=str(path.parent)) as tmp:
            tmp.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
            tmp_path = Path(tmp.name)
        tmp_path.replace(path)


def _iter_memos() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in MEMOS_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            rows.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return rows


def _write_memos(rows: List[Dict[str, Any]]) -> None:
    with _file_lock(MEMOS_PATH):
        text = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
        MEMOS_PATH.write_text((text + "\n") if text else "", encoding="utf-8")


def _append_memo(row: Dict[str, Any]) -> None:
    with _file_lock(MEMOS_PATH):
        with MEMOS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _append_review_log(row: Dict[str, Any]) -> None:
    with _file_lock(REVIEW_LOG_PATH):
        with REVIEW_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


def _iter_review_log() -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for line in REVIEW_LOG_PATH.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            rows.append(json.loads(s))
        except json.JSONDecodeError:
            continue
    return rows


def _normalize_memo_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip())


def _parse_iso_datetime(value: str) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _coerce_to_runtime_tz(dt: datetime, config: RuntimeConfig) -> datetime:
    tz = _tz(config)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=tz)
    return dt.astimezone(tz)


def _parse_yyyy_mm_dd(value: str) -> Optional[datetime]:
    try:
        return datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return None


def add_memo(text: str, category: str = "LEARNING", tags: Optional[List[str]] = None) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    normalized = _normalize_memo_text(text)
    if not normalized:
        raise ValueError("memo text is empty")

    date_key = now.date().isoformat()
    for row in _iter_memos():
        created = row.get("created_at", "")
        if created.startswith(date_key) and _normalize_memo_text(row.get("content", "")) == normalized:
            return {"status": "deduped", "memo": row}

    memo = {
        "id": str(uuid.uuid4()),
        "content": normalized,
        "category": category,
        "tags": tags or [],
        "created_at": now.isoformat(),
        "updated_at": now.isoformat(),
    }
    _append_memo(memo)
    return {"status": "created", "memo": memo}


def query_memos(days: int = 7) -> List[Dict[str, Any]]:
    config = _read_runtime()
    now = _now_local(config)
    start = (now - timedelta(days=max(days - 1, 0))).date()
    out: List[Dict[str, Any]] = []
    for row in _iter_memos():
        created = row.get("created_at")
        if not created:
            continue
        dt = _parse_iso_datetime(created)
        if not dt:
            continue
        dt = _coerce_to_runtime_tz(dt, config)
        if dt.date() >= start:
            out.append(row)
    out.sort(key=lambda x: x.get("created_at", ""), reverse=True)
    return out


def _parse_once_time(expr: str, now: datetime) -> Optional[datetime]:
    m = re.search(r"(\d+)\s*(分钟|分)后", expr)
    if m:
        return now + timedelta(minutes=int(m.group(1)))

    m = re.search(r"(\d+)\s*(小时|h|H)后", expr)
    if m:
        return now + timedelta(hours=int(m.group(1)))

    m = re.search(r"明天\s*(上午|下午|晚上)?\s*(\d{1,2})(?:[:点](\d{1,2}))?", expr)
    if m:
        period = m.group(1) or ""
        hour = int(m.group(2))
        minute = int(m.group(3) or 0)
        if period in ("下午", "晚上") and hour < 12:
            hour += 12
        base = (now + timedelta(days=1)).replace(hour=hour, minute=minute, second=0, microsecond=0)
        return base

    return None


def _extract_message(expr: str) -> str:
    m = re.search(r"提醒我(.+)$", expr)
    if m:
        return m.group(1).strip()
    return expr.strip()


def _load_reminders() -> List[Dict[str, Any]]:
    return _read_json_array(REMINDERS_PATH)


def _save_reminders(reminders: List[Dict[str, Any]]) -> None:
    _write_json_array(REMINDERS_PATH, reminders)


def add_once_reminder(expr: str) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    fire_at = _parse_once_time(expr, now)
    if fire_at is None:
        raise ValueError("could not parse once reminder time")
    message = _extract_message(expr)
    if not message:
        raise ValueError("reminder message is empty")

    reminders = _load_reminders()
    dedupe_key = f"ONCE::{message}::{fire_at.isoformat()}"
    for row in reminders:
        if row.get("status") in ("SCHEDULED", "PENDING_NOTIFY") and row.get("dedupe_key") == dedupe_key:
            return {"status": "deduped", "reminder": row}

    reminder = {
        "id": str(uuid.uuid4()),
        "type": "ONCE",
        "message": message,
        "timezone": config.timezone_name,
        "trigger_time": fire_at.isoformat(),
        "next_fire": fire_at.isoformat(),
        "status": "SCHEDULED",
        "created_at": now.isoformat(),
        "last_fired_at": None,
        "dedupe_key": dedupe_key,
        "delivery_attempts": 0,
        "next_retry": None,
        "last_delivery_error": None,
    }
    reminders.append(reminder)
    _save_reminders(reminders)
    return {"status": "created", "reminder": reminder}


def add_daily_reminder(time_text: str, message: str) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)

    m = re.match(r"^\s*(\d{1,2})(?:[:点](\d{1,2}))?\s*$", time_text)
    if not m:
        raise ValueError("daily time must be HH:mm or H点")
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    if hour < 0 or hour > 23 or minute < 0 or minute > 59:
        raise ValueError("invalid daily time")

    next_fire = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if next_fire <= now:
        next_fire = next_fire + timedelta(days=1)

    reminders = _load_reminders()
    dedupe_key = f"DAILY::{message}::{hour:02d}:{minute:02d}"
    for row in reminders:
        if row.get("status") in ("SCHEDULED", "PENDING_NOTIFY") and row.get("dedupe_key") == dedupe_key:
            return {"status": "deduped", "reminder": row}

    reminder = {
        "id": str(uuid.uuid4()),
        "type": "DAILY",
        "message": message.strip(),
        "timezone": config.timezone_name,
        "trigger_time": f"{hour:02d}:{minute:02d}",
        "next_fire": next_fire.isoformat(),
        "status": "SCHEDULED",
        "created_at": now.isoformat(),
        "last_fired_at": None,
        "dedupe_key": dedupe_key,
        "delivery_attempts": 0,
        "next_retry": None,
        "last_delivery_error": None,
    }
    reminders.append(reminder)
    _save_reminders(reminders)
    return {"status": "created", "reminder": reminder}


def cancel_reminder(reminder_id: str) -> Dict[str, Any]:
    reminders = _load_reminders()
    hit = None
    for row in reminders:
        if row.get("id") == reminder_id:
            row["status"] = "CANCELLED"
            row["next_retry"] = None
            hit = row
            break
    _save_reminders(reminders)
    return {"status": "ok", "reminder": hit}


def scan_due() -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    reminders = _load_reminders()

    due: List[Dict[str, Any]] = []
    for row in reminders:
        status = row.get("status")
        if status not in ("SCHEDULED", "PENDING_NOTIFY"):
            continue

        attempts = int(row.get("delivery_attempts", 0))
        if status == "PENDING_NOTIFY" and attempts >= config.max_delivery_attempts:
            row["status"] = "FAILED"
            row["last_delivery_error"] = row.get("last_delivery_error") or "max delivery attempts reached"
            continue

        retry_at_text = row.get("next_retry")
        if retry_at_text:
            retry_at = _parse_iso_datetime(retry_at_text)
            if retry_at and _coerce_to_runtime_tz(retry_at, config) > now:
                continue

        next_fire = _parse_iso_datetime(str(row.get("next_fire", "")))
        if not next_fire:
            continue
        next_fire = _coerce_to_runtime_tz(next_fire, config)
        if next_fire > now:
            continue

        row["status"] = "PENDING_NOTIFY"
        row["delivery_attempts"] = attempts + 1
        row["last_claimed_at"] = now.isoformat()
        row["next_retry"] = None
        due.append(row)

    _save_reminders(reminders)
    if len(due) > config.max_scan_batch:
        due = due[: config.max_scan_batch]
    return {"now": now.isoformat(), "due": due}


def ack_reminder(reminder_id: str) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    reminders = _load_reminders()
    hit = None

    for row in reminders:
        if row.get("id") != reminder_id:
            continue
        hit = row
        if row.get("status") not in ("PENDING_NOTIFY", "SCHEDULED"):
            break

        row["last_fired_at"] = now.isoformat()
        row["last_delivery_error"] = None
        row["next_retry"] = None

        if row.get("type") == "ONCE":
            row["status"] = "FIRED"
        elif row.get("type") == "DAILY":
            next_fire = _parse_iso_datetime(str(row.get("next_fire", ""))) or now
            next_fire = _coerce_to_runtime_tz(next_fire, config)
            while next_fire <= now:
                next_fire = next_fire + timedelta(days=1)
            row["next_fire"] = next_fire.isoformat()
            row["status"] = "SCHEDULED"
            row["delivery_attempts"] = 0
        break

    _save_reminders(reminders)
    return {"status": "ok", "reminder": hit}


def fail_reminder(reminder_id: str, error_message: str = "delivery failed") -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    reminders = _load_reminders()
    hit = None

    for row in reminders:
        if row.get("id") != reminder_id:
            continue
        hit = row
        attempts = int(row.get("delivery_attempts", 0))
        row["last_delivery_error"] = error_message

        if attempts >= config.max_delivery_attempts:
            row["status"] = "FAILED"
            row["next_retry"] = None
        else:
            row["status"] = "SCHEDULED"
            row["next_retry"] = (now + timedelta(seconds=config.retry_delay_seconds)).isoformat()
        break

    _save_reminders(reminders)
    return {"status": "ok", "reminder": hit}


def _review_done_map() -> Dict[str, str]:
    done: Dict[str, str] = {}
    for row in _iter_review_log():
        key = f"{row.get('memo_id')}::{row.get('stage')}"
        done[key] = row.get("reviewed_at", "")
    return done


def _build_review_rows(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    due_only: bool = False,
) -> List[Dict[str, Any]]:
    config = _read_runtime()
    now = _now_local(config)
    today = now.date()

    start_date = _parse_yyyy_mm_dd(from_date).date() if from_date else None
    end_date = _parse_yyyy_mm_dd(to_date).date() if to_date else None

    done_map = _review_done_map()
    rows: List[Dict[str, Any]] = []

    for memo in _iter_memos():
        created = memo.get("created_at", "")
        created_dt = _parse_iso_datetime(created)
        if not created_dt:
            continue
        created_dt = _coerce_to_runtime_tz(created_dt, config)
        memo_date = created_dt.date()

        for idx, interval in enumerate(REVIEW_INTERVAL_DAYS):
            review_date = memo_date + timedelta(days=interval)
            if start_date and review_date < start_date:
                continue
            if end_date and review_date > end_date:
                continue

            stage = f"R{idx + 1}"
            done_key = f"{memo.get('id')}::{stage}"
            reviewed_at = done_map.get(done_key)

            if reviewed_at:
                status = "DONE"
            elif review_date < today:
                status = "OVERDUE"
            elif review_date == today:
                status = "DUE"
            else:
                status = "UPCOMING"

            if due_only and status not in ("DUE", "OVERDUE"):
                continue

            rows.append(
                {
                    "review_date": review_date.isoformat(),
                    "stage": stage,
                    "interval_days": interval,
                    "status": status,
                    "memo_id": memo.get("id"),
                    "memo_created_date": memo_date.isoformat(),
                    "content": memo.get("content", ""),
                    "reviewed_at": reviewed_at,
                }
            )

    rows.sort(
        key=lambda x: (
            x.get("review_date", ""),
            int(str(x.get("stage", "R0")).replace("R", "") or "0"),
            x.get("memo_created_date", ""),
        )
    )
    return rows


def _rows_to_markdown(rows: List[Dict[str, Any]]) -> str:
    lines = [
        "| 复习日期 | 阶段 | 状态 | 记录日期 | 内容 |",
        "|---|---|---|---|---|",
    ]
    for row in rows:
        content = str(row.get("content", "")).replace("|", "/")
        lines.append(
            "| {review_date} | {stage} | {status} | {memo_created_date} | {content} |".format(
                review_date=row.get("review_date", ""),
                stage=row.get("stage", ""),
                status=row.get("status", ""),
                memo_created_date=row.get("memo_created_date", ""),
                content=content,
            )
        )
    if len(lines) == 2:
        lines.append("| - | - | - | - | 暂无复习项 |")
    return "\n".join(lines)


def get_review_table(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    due_only: bool = False,
) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)

    rows = _build_review_rows(from_date=from_date, to_date=to_date, due_only=due_only)
    markdown = _rows_to_markdown(rows)

    REVIEW_TABLE_PATH.write_text(
        json.dumps(rows, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    grouped: Dict[str, List[Dict[str, Any]]] = {}
    for row in rows:
        key = row["review_date"]
        grouped.setdefault(key, []).append(row)

    grouped_rows = [{"date": d, "items": grouped[d]} for d in sorted(grouped.keys())]
    return {
        "status": "ok",
        "generated_at": now.isoformat(),
        "count": len(rows),
        "table": grouped_rows,
        "markdown_table": markdown,
        "stored_path": str(REVIEW_TABLE_PATH),
    }


def mark_review_done(memo_id: str, stage: str) -> Dict[str, Any]:
    config = _read_runtime()
    now = _now_local(config)
    stage_text = stage.strip().upper()
    if not re.match(r"^R[1-6]$", stage_text):
        raise ValueError("stage must be R1..R6")

    row = {
        "id": str(uuid.uuid4()),
        "memo_id": memo_id,
        "stage": stage_text,
        "reviewed_at": now.isoformat(),
    }
    _append_review_log(row)
    return {"status": "created", "review": row}


def normalize_timezones() -> Dict[str, Any]:
    config = _read_runtime()
    updated_memos = 0
    updated_reminders = 0

    memos = _iter_memos()
    for row in memos:
        for key in ("created_at", "updated_at"):
            dt = _parse_iso_datetime(str(row.get(key, "")))
            if not dt:
                continue
            row[key] = _coerce_to_runtime_tz(dt, config).isoformat()
            updated_memos += 1
    _write_memos(memos)

    reminders = _load_reminders()
    for row in reminders:
        row["timezone"] = config.timezone_name
        for key in ("trigger_time", "next_fire", "created_at", "last_fired_at", "next_retry", "last_claimed_at"):
            value = row.get(key)
            if not isinstance(value, str) or not value:
                continue
            dt = _parse_iso_datetime(value)
            if not dt:
                continue
            row[key] = _coerce_to_runtime_tz(dt, config).isoformat()
            updated_reminders += 1
    _save_reminders(reminders)

    return {
        "status": "ok",
        "memos_fields_normalized": updated_memos,
        "reminder_fields_normalized": updated_reminders,
        "timezone": config.timezone_name,
    }


def ingest(text: str) -> Dict[str, Any]:
    clean = text.strip()
    if not clean:
        raise ValueError("input is empty")

    if any(x in clean for x in ["艾宾浩斯", "遗忘曲线", "复习表", "复习计划"]):
        due_only = "待复习" in clean or "今天要复习" in clean
        return get_review_table(due_only=due_only)

    if "提醒我" in clean and ("每天" in clean or "每日" in clean):
        m = re.search(r"每(?:天|日)\s*(\d{1,2}(?::\d{1,2}|点\d{0,2})?)\s*提醒我(.+)$", clean)
        if m:
            return add_daily_reminder(m.group(1).replace("点", ":"), m.group(2).strip())

    if "提醒我" in clean and ("后" in clean or "明天" in clean):
        return add_once_reminder(clean)

    if any(x in clean for x in ["今天我做了什么", "最近7天", "最近"]):
        rows = query_memos(7)
        return {"status": "ok", "result": rows}

    # Default: record memo, stripping common prefixes.
    stripped = re.sub(r"^(我今天(做了|学了)|记录[:：]?|我今天)\s*", "", clean)
    return add_memo(stripped or clean)


def _print(payload: Any) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def main() -> None:
    _ensure_data_files()

    parser = argparse.ArgumentParser(description="OpenClaw memo skill runtime")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_add = sub.add_parser("add-memo")
    p_add.add_argument("--text", required=True)
    p_add.add_argument("--category", default="LEARNING")
    p_add.add_argument("--tags", default="")

    p_query = sub.add_parser("query")
    p_query.add_argument("--days", type=int, default=7)

    p_once = sub.add_parser("add-once")
    p_once.add_argument("--expr", required=True)

    p_daily = sub.add_parser("add-daily")
    p_daily.add_argument("--time", required=True)
    p_daily.add_argument("--message", required=True)

    p_cancel = sub.add_parser("cancel")
    p_cancel.add_argument("--id", required=True)

    p_ack = sub.add_parser("ack-reminder")
    p_ack.add_argument("--id", required=True)

    p_fail = sub.add_parser("fail-reminder")
    p_fail.add_argument("--id", required=True)
    p_fail.add_argument("--error", default="delivery failed")

    sub.add_parser("scan-due")

    p_review_table = sub.add_parser("review-table")
    p_review_table.add_argument("--from-date", default="")
    p_review_table.add_argument("--to-date", default="")
    p_review_table.add_argument("--due-only", action="store_true")

    p_review_done = sub.add_parser("review-done")
    p_review_done.add_argument("--memo-id", required=True)
    p_review_done.add_argument("--stage", required=True)

    sub.add_parser("normalize-timezones")

    p_ingest = sub.add_parser("ingest")
    p_ingest.add_argument("--text", required=True)

    args = parser.parse_args()

    if args.cmd == "add-memo":
        tags = [x.strip() for x in args.tags.split(",") if x.strip()]
        _print(add_memo(args.text, category=args.category, tags=tags))
    elif args.cmd == "query":
        _print({"status": "ok", "result": query_memos(days=args.days)})
    elif args.cmd == "add-once":
        _print(add_once_reminder(args.expr))
    elif args.cmd == "add-daily":
        _print(add_daily_reminder(args.time, args.message))
    elif args.cmd == "cancel":
        _print(cancel_reminder(args.id))
    elif args.cmd == "ack-reminder":
        _print(ack_reminder(args.id))
    elif args.cmd == "fail-reminder":
        _print(fail_reminder(args.id, args.error))
    elif args.cmd == "scan-due":
        _print(scan_due())
    elif args.cmd == "review-table":
        _print(
            get_review_table(
                from_date=args.from_date or None,
                to_date=args.to_date or None,
                due_only=bool(args.due_only),
            )
        )
    elif args.cmd == "review-done":
        _print(mark_review_done(args.memo_id, args.stage))
    elif args.cmd == "normalize-timezones":
        _print(normalize_timezones())
    elif args.cmd == "ingest":
        _print(ingest(args.text))


if __name__ == "__main__":
    main()
