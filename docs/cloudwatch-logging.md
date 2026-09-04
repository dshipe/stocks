# CloudWatch Logging — Runbook

## What this is

Every scanner and trading script now mirrors its output to AWS CloudWatch Logs, in addition to the existing local `>> file.log` redirection from `cron_setup.sh`. Local logging is unchanged — this only adds a second destination.

**Scripts wired up** (`scan/shared/cloudwatch_logging.py`, one `enable_cloudwatch_logging("<name>")` call each):

| Script | CloudWatch log stream |
|---|---|
| `scan/watchlist_scanner.py` | `watchlist_scanner` |
| `scan/breakout_scanner.py` | `breakout_scanner` |
| `scan/performance_tracker.py` | `performance_tracker` |
| `scan/schwab_scripts/schwab_stop_loss.py` | `schwab_stop_loss` |
| `scan/schwab_scripts/check_profit_targets.py` | `check_profit_targets` |
| `scan/paper_trading_bot.py` | `paper_trading_bot` |
| `congress_trades/pelosi_alert.py` | `pelosi_alert` |

All seven write to one log group (default `/stock-scanner`), one stream per script, so you can watch them together or individually.

## How it works

This codebase's scripts mix plain `print()` (most of the operational output — scan summaries, trade decisions) and the `logging` module (`logger.warning(...)` etc.), so `cloudwatch_logging.py` catches both:

1. **`logging` calls** — a `watchtower.CloudWatchLogHandler` is attached to the root logger, so every module's `logging.getLogger(__name__)` reaches it, regardless of import order.
2. **`print()` calls** — `sys.stdout`/`sys.stderr` are wrapped in a tee that writes to the real stream (so your existing `.log` files are unaffected) **and** forwards each line to the same CloudWatch handler.

**It never crashes the calling script.** If CloudWatch is unreachable for any reason — no IAM role, `boto3`/`watchtower` not installed, wrong region, network blocked — `enable_cloudwatch_logging()` catches the exception, prints one line (`[cloudwatch_logging] CloudWatch unavailable, continuing local-only: ...`), and the script proceeds exactly as it did before this change. This was verified locally by deliberately pointing `AWS_CONFIG_FILE`/`AWS_SHARED_CREDENTIALS_FILE` at nonexistent paths and confirming `paper_trading_bot.py` and `breakout_scanner.py` still run to completion with exit code 0.

## Setup (run this on the EC2 box — not done yet)

### 1. IAM

Attach a role to the EC2 instance (or add to its existing role) with a policy scoped to this log group prefix:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "logs:CreateLogGroup",
        "logs:CreateLogStream",
        "logs:PutLogEvents",
        "logs:DescribeLogStreams"
      ],
      "Resource": "arn:aws:logs:*:*:log-group:/stock-scanner*"
    }
  ]
}
```

### 2. Dependencies

```bash
cd /path/to/scan
pip install -r requirements.txt   # adds boto3 + watchtower
```

### 3. Region

Defaults to `us-east-1` if `AWS_REGION` isn't set (matches the Schwab Lambda endpoint's region already used elsewhere in this codebase). If your EC2 instance runs elsewhere, set it once for every cron job by adding a line at the top of the crontab itself (not in a shell profile — cron's own environment is minimal and won't read `.bashrc`/`.profile`):

```
AWS_REGION=us-west-2
```
(`crontab -e`, add that line above the job entries — `cron_setup.sh` doesn't manage this line, add it manually.)

### 4. That's it

No separate CloudWatch agent needed — this is code-level, not file-tailing. Just the IAM role + `pip install -r requirements.txt`, then the next cron run starts mirroring.

## Viewing logs

**Console**: CloudWatch → Log groups → `/stock-scanner` → pick a stream.

**CLI**, tail everything live:
```bash
aws logs tail /stock-scanner --follow
```
One script only:
```bash
aws logs tail /stock-scanner --follow --log-stream-names paper_trading_bot
```
Just errors, last 24h:
```bash
aws logs filter-log-events --log-group-name /stock-scanner --filter-pattern "ERROR" --start-time $(( ($(date +%s) - 86400) * 1000 ))
```

## Useful CloudWatch Alarms to consider (not set up yet)

- **Missing heartbeat**: alarm if `paper_trading_bot` or `breakout_scanner` haven't logged anything in >24h on a trading day — catches the cron silently dying, exactly the class of bug that caused `breakout_entries` to sit at zero rows for months.
- **Error rate**: metric filter on `"ERROR"` or `"[cloudwatch_logging] CloudWatch unavailable"` across the log group, alarm on any occurrence.

## Troubleshooting

| Symptom | Likely cause |
|---|---|
| `[cloudwatch_logging] CloudWatch unavailable ... could not be found` | No IAM role attached, or wrong profile/credentials in the cron environment |
| `AccessDenied` in the notice | IAM policy missing `logs:CreateLogGroup` (first run) or `logs:PutLogEvents` |
| Logs appear locally but not in CloudWatch, no error printed | Check `boto3`/`watchtower` actually installed in the same Python environment cron uses (`which python3` inside the crontab's `$PYTHON` var, not just your interactive shell) |
| Wrong region errors | Set `AWS_REGION` in the crontab as shown above |

## Cost

CloudWatch Logs bills per GB ingested plus storage. This is low-volume text logging (a handful of scripts, a few runs/day) — expect a negligible cost, but if you want to cap it, set a retention policy on the log group (default is "never expire"):
```bash
aws logs put-retention-policy --log-group-name /stock-scanner --retention-in-days 30
```

## What was NOT done

This was built and verified for safe local fallback behavior only. **No CloudWatch resources have been created** — I don't have access to whatever AWS account hosts the EC2 stock-trading instance (my local AWS credentials resolve to an unrelated work account, and I deliberately did not use them here). The IAM role, `pip install`, and first real end-to-end verification against a live log group all still need to happen on the EC2 box, using its own AWS account.
