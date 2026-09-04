"""
cloudwatch_logging.py -- Mirror a script's output to AWS CloudWatch Logs, in
addition to whatever local redirection cron already does (`>> file.log`).

Two things get mirrored, since this codebase's scripts use both:
  1. Anything logged via the `logging` module (logger.info/warning/error) --
     caught by attaching a CloudWatchLogHandler to the ROOT logger, so it
     picks up every module's logger regardless of import order.
  2. Plain print() output (most of this codebase's operational output --
     scan summaries, trade decisions -- is print(), not logging) -- caught by
     wrapping sys.stdout/sys.stderr in a tee that writes to the real stream
     AND forwards each line to the same CloudWatch handler.

Local behavior is completely unchanged either way -- this only ADDS a mirror,
it never replaces the existing console/file output.

Requires `boto3` + `watchtower` (see scan/requirements.txt) and an IAM role
attached to the EC2 instance permitting logs:CreateLogGroup/CreateLogStream/
PutLogEvents on the log group used (default: /stock-scanner/<script_name> --
see docs/cloudwatch-logging.md for the exact policy and setup steps).

If CloudWatch is unreachable for any reason (no IAM role, no boto3/watchtower
installed, wrong region, network blocked) this degrades to local-only with a
single one-line notice -- it must never be the reason a scanner or trading
script crashes. This is an observability add-on, not a dependency.

Usage (call once, near the top of the script, right after logging.basicConfig
if the script has one):
    from shared.cloudwatch_logging import enable_cloudwatch_logging
    enable_cloudwatch_logging("breakout_scanner")
"""

import logging
import os
import sys

LOG_GROUP_PREFIX = os.getenv("CLOUDWATCH_LOG_GROUP_PREFIX", "/stock-scanner")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

_enabled_for: set[str] = set()  # guard against double-wrapping on re-import/re-call


class _TeeToLogger:
    """File-like object: mirrors writes to the real stream AND a logger, line by line."""

    def __init__(self, real_stream, logger: logging.Logger, level: int):
        self._real = real_stream
        self._logger = logger
        self._level = level
        self._buffer = ""

    def write(self, data: str) -> int:
        self._real.write(data)
        self._buffer += data
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            if line.strip():
                self._logger.log(self._level, line)
        return len(data)

    def flush(self):
        self._real.flush()

    def isatty(self) -> bool:
        return False

    def __getattr__(self, name):
        # Delegate anything else (encoding, reconfigure, etc.) to the real stream
        return getattr(self._real, name)


def enable_cloudwatch_logging(script_name: str, log_group: str | None = None) -> bool:
    """
    Mirror this process's stdout/stderr/logging output to CloudWatch Logs
    under <log_group or LOG_GROUP_PREFIX>, stream name = script_name.
    Returns True if CloudWatch mirroring was enabled, False if it fell back
    to local-only. Never raises.
    """
    if script_name in _enabled_for:
        return True
    try:
        import boto3
        import watchtower

        group = log_group or LOG_GROUP_PREFIX
        client = boto3.client("logs", region_name=AWS_REGION)

        handler = watchtower.CloudWatchLogHandler(
            log_group_name=group,
            log_stream_name=script_name,
            boto3_client=client,
            create_log_group=True,
            send_interval=10,
        )
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))

        # (1) every logging.getLogger(...) call anywhere in the process
        logging.getLogger().addHandler(handler)

        # (2) plain print() output
        mirror_logger = logging.getLogger(f"cloudwatch.stdio.{script_name}")
        mirror_logger.setLevel(logging.INFO)
        mirror_logger.propagate = False
        mirror_logger.addHandler(handler)
        sys.stdout = _TeeToLogger(sys.stdout, mirror_logger, logging.INFO)
        sys.stderr = _TeeToLogger(sys.stderr, mirror_logger, logging.ERROR)

        _enabled_for.add(script_name)
        print(f"[cloudwatch_logging] mirroring to log group '{group}', stream '{script_name}'")
        return True
    except Exception as e:
        print(f"[cloudwatch_logging] CloudWatch unavailable, continuing local-only: {e}")
        return False
