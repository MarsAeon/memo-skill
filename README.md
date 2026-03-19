# OpenClaw 学习备忘录 Skill

一个轻量级学习/待办备忘录 Skill，用于记录日常内容、定时提醒，以及按艾宾浩斯间隔生成复习表。

## 功能概览
- 自然语言记录：例如“我今天做了……”“我今天学了……”。
- 近 N 天查询：默认最近 7 天。
- 一次性提醒：例如 `X分钟后`、`X小时后`、`明天...`。
- 每日循环提醒：例如“每天 09:00 提醒我……”。
- 到期提醒扫描：供 OpenClaw 定时任务调用。
- 艾宾浩斯复习表：按日期汇总全部复习项（覆盖不同日期记录的内容）。

## 目录结构
- `SKILL.md`：Skill 元信息与运行契约。
- `src/memo_skill.py`：核心运行时。
- `src/openclaw_adapter.py`：OpenClaw 统一 JSON 适配器入口。
- `config/runtime.json`：运行配置（时区、扫描间隔、重试策略等）。
- `config/runtime.prod.json`：生产建议配置。
- `data/`：持久化数据目录。
- `handlers/` 与 `templates/`：行为规则与提示模板。

## 核心命令
在仓库根目录执行：

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

## 艾宾浩斯复习表
- 固定间隔：`1, 2, 4, 7, 15, 30` 天。
- 复习表会按“复习日期”聚合，并落盘到 `data/review_table.json`。
- 可以通过 `ingest` 触发语句查看，例如“查看艾宾浩斯复习表”“查看遗忘曲线提醒”。
- 每行包含：复习日期、阶段、状态、记录日期、内容。

## OpenClaw 接入说明
### 推荐方式：统一 JSON 适配器（单入口）
建议 OpenClaw 只接一个命令入口：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\openclaw_adapter.ps1 '{"action":"ingest","text":"我今天做了接口联调"}'
```

支持的 `action`：
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

定时任务请求示例：

```json
{"action":"scan_due"}
```

回调示例：

```json
{"action":"ack","id":"<reminder-id>"}
{"action":"fail","id":"<reminder-id>","error":"push failed"}
```

### 备选方式：直接调用 CLI
1. 对话阶段：
- 调用 `ingest --text "<user input>"`。

2. 定时阶段：
- OpenClaw 每 60 秒执行一次 `scan-due`。
- 对每条 `due` 结果发送通知。
- 发送成功调用 `ack-reminder --id <id>`。
- 发送失败调用 `fail-reminder --id <id> --error "..."`。

3. 重试策略：
- `scan-due` 领取后状态为 `PENDING_NOTIFY`。
- `fail-reminder` 会设置 `next_retry`（默认 60 秒后重试）。
- 超过最大重试次数（`max_delivery_attempts`）后状态变为 `FAILED`。

4. 取消提醒：
- 调用 `python .\src\memo_skill.py cancel --id <reminder_id>`。

## 生产上线检查清单
1. 使用 `config/runtime.prod.json` 的配置值。
2. 首次上线前执行一次 `normalize-timezones`。
3. 配置 OpenClaw 定时任务每 60 秒执行 `scripts/openclaw_scan.ps1` 或适配器 `scan_due` action。
4. 确保通知工作流接入 ACK/FAIL 回调。
5. 监控 `FAILED` 提醒并按需人工重试。

## 备注
- 默认时区来自 `config/runtime.json`（默认 `Asia/Shanghai`）。
- 去重规则：
  - 备忘：同一天 + 同内容（归一化后）去重。
  - 提醒：同类型 + 同消息 + 同触发时间去重。
- 当前实现已包含艾宾浩斯复习表与记录能力。
