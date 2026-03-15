# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml"]
# ///
"""Claude Cron Registry — manage.py

Single entry point for all cron registry operations.
Called by crontab for job execution, and by user for management.

Usage:
    uv run manage.py run <job>
    uv run manage.py install
    uv run manage.py uninstall
    uv run manage.py status
    uv run manage.py validate
    uv run manage.py enable <job>
    uv run manage.py disable <job>
    uv run manage.py delete <job>
    uv run manage.py logs <job> [-n N]
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CRON_DIR = Path(__file__).resolve().parent

def _find_project_root() -> Path:
    """Find project root via git, falling back to directory traversal."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, cwd=CRON_DIR,
        )
        if result.returncode == 0:
            return Path(result.stdout.strip())
    except FileNotFoundError:
        pass
    # Fallback: walk up from CRON_DIR until we find a .git directory
    for parent in CRON_DIR.parents:
        if (parent / ".git").exists():
            return parent
    return CRON_DIR.parent

PROJECT_ROOT = _find_project_root()
REGISTRY_PATH = CRON_DIR / "registry.yaml"
ENV_PATH = CRON_DIR / ".env"
LOGS_DIR = CRON_DIR / "logs"
LOCKS_DIR = CRON_DIR / "locks"
STDERR_LOG = LOGS_DIR / "cron-stderr.log"

CRONTAB_BEGIN = "# === CLAUDE-CRON-BEGIN (managed by platforms/claude_platform/cron/manage.py — do not edit) ==="
CRONTAB_END = "# === CLAUDE-CRON-END ==="

JOB_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
CRON_SCHEDULE_RE = re.compile(
    r"^(\*|[0-9,/*-]+)\s+(\*|[0-9,/*-]+)\s+(\*|[0-9,/*-]+)\s+(\*|[0-9,/*-]+)\s+(\*|[0-9,/*-]+)$"
)

STATUS_ICONS = {
    "success": "\U0001f7e2",       # 🟢
    "failure": "\U0001f534",       # 🔴
    "timeout": "\U0001f7e1",       # 🟡
    "skipped": "\u26aa",           # ⚪
    "already_running": "\u26aa",   # ⚪
    "runner_error": "\U0001f7e0",  # 🟠
}

# ---------------------------------------------------------------------------
# Registry loading
# ---------------------------------------------------------------------------


def load_registry() -> dict[str, Any]:
    """Load and parse registry.yaml."""
    if not REGISTRY_PATH.exists():
        print(f"Error: {REGISTRY_PATH} not found", file=sys.stderr)
        sys.exit(1)
    with open(REGISTRY_PATH) as f:
        return yaml.safe_load(f)


def get_job_config(registry: dict[str, Any], job_name: str) -> dict[str, Any]:
    """Get merged config for a job (defaults + job overrides)."""
    defaults = registry.get("defaults", {})
    jobs = registry.get("jobs") or {}

    if job_name not in jobs:
        print(f"Error: job '{job_name}' not found in registry", file=sys.stderr)
        sys.exit(1)

    # Deep merge: defaults as base, job overrides
    config = {}
    for key, value in defaults.items():
        if isinstance(value, dict):
            config[key] = dict(value)
        else:
            config[key] = value

    for key, value in jobs[job_name].items():
        if isinstance(value, dict) and key in config and isinstance(config[key], dict):
            config[key].update(value)
        else:
            config[key] = value

    return config


def validate_job_name(name: str) -> bool:
    """Validate job name: [a-z0-9-], must start with alphanumeric."""
    return bool(JOB_NAME_RE.match(name))


def validate_schedule(schedule: str) -> bool:
    """Validate 5-field cron expression with range checks."""
    m = CRON_SCHEDULE_RE.match(schedule.strip())
    if not m:
        return False
    # Range checks: minute(0-59), hour(0-23), day(1-31), month(1-12), dow(0-7)
    max_values = [59, 23, 31, 12, 7]
    for field, max_val in zip(m.groups(), max_values):
        if field == "*":
            continue
        # Extract all numeric values from the field (handles 1,5,10 and 1-5 and */2)
        for part in field.split(","):
            part = part.split("/")[0]  # strip step (e.g., */2 → *)
            if part == "*":
                continue
            for bound in part.split("-"):
                try:
                    val = int(bound)
                    if val < 0 or val > max_val:
                        return False
                except ValueError:
                    return False
    return True


# ---------------------------------------------------------------------------
# .env loading
# ---------------------------------------------------------------------------


def load_env_file() -> None:
    """Load .env file into os.environ (setdefault, no override)."""
    if not ENV_PATH.exists():
        return
    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


# ---------------------------------------------------------------------------
# Lock
# ---------------------------------------------------------------------------


def acquire_lock(job_name: str) -> int | None:
    """Acquire flock for a job. Returns fd on success, None if already locked."""
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)
    lock_path = LOCKS_DIR / f"{job_name}.lock"
    fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except OSError:
        os.close(fd)
        return None


# ---------------------------------------------------------------------------
# Claude execution
# ---------------------------------------------------------------------------


def build_claude_command(config: dict[str, Any]) -> list[str]:
    """Build claude CLI command from job config."""
    claude_path = shutil.which("claude")
    if not claude_path:
        raise RuntimeError("claude command not found in PATH")

    cmd = [
        claude_path,
        "-p",
        config["prompt"],
        "--output-format", "json",
        "--model", config.get("model", "sonnet"),
        "--max-turns", str(config.get("max_turns", 20)),
    ]

    budget = config.get("max_budget_usd")
    if budget is not None:
        cmd.extend(["--max-budget-usd", str(budget)])

    tools = config.get("allowed_tools")
    if tools:
        cmd.extend(["--allowedTools", ",".join(tools)])

    if config.get("no_session_persistence", True):
        cmd.append("--no-session-persistence")

    return cmd


def run_claude(config: dict[str, Any], job_name: str) -> dict[str, Any]:
    """Execute claude and return structured result."""
    started_at = datetime.now(timezone.utc).astimezone()
    run_id = started_at.strftime("%Y%m%d-%H%M%S")

    log_dir = LOGS_DIR / job_name
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{run_id}.log"

    result = {
        "run_id": run_id,
        "job": job_name,
        "status": "runner_error",
        "exit_code": -1,
        "started_at": started_at.isoformat(),
        "finished_at": "",
        "duration_sec": 0,
        "cost_usd": 0.0,
        "tokens": {"input": 0, "output": 0},
        "model": config.get("model", "sonnet"),
        "log_path": str(log_path.relative_to(CRON_DIR)),
        "summary": "",
    }

    try:
        cmd = build_claude_command(config)
    except RuntimeError as e:
        result["summary"] = str(e)
        return result

    timeout_sec = config.get("timeout_sec", 300)

    # Unset CLAUDECODE to allow execution from within another Claude session
    env = dict(os.environ)
    env.pop("CLAUDECODE", None)
    env.pop("CLAUDE_CODE_ENTRYPOINT", None)

    # Merge per-job env vars from registry config
    for k, v in config.get("env", {}).items():
        env[k] = str(v)

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout_sec,
            env=env,
            cwd=PROJECT_ROOT,
        )
        raw_output = proc.stdout
        result["exit_code"] = proc.returncode
        result["status"] = "success" if proc.returncode == 0 else "failure"

        if proc.stderr:
            raw_output += f"\n--- stderr ---\n{proc.stderr}"

    except subprocess.TimeoutExpired as e:
        raw_output = (e.stdout or "") if isinstance(e.stdout, str) else (e.stdout or b"").decode(errors="replace")
        result["status"] = "timeout"
        result["exit_code"] = -1
        result["summary"] = f"Timed out after {timeout_sec}s"

    # Save raw log
    log_path.write_text(raw_output, encoding="utf-8")

    # Parse JSON output from claude for cost/token info
    try:
        # claude --output-format json wraps output in a JSON object
        claude_json = json.loads(proc.stdout if result["status"] != "timeout" else "{}")
        usage = claude_json.get("usage", {})
        result["tokens"]["input"] = usage.get("input_tokens", 0)
        result["tokens"]["output"] = usage.get("output_tokens", 0)
        result["cost_usd"] = claude_json.get("total_cost_usd", 0.0)

        # Extract the actual response text for summary
        response_text = claude_json.get("result", "")
        if isinstance(response_text, str) and response_text:
            # Take first 200 chars as summary, stripping newlines
            summary = response_text.replace("\n", " ").strip()
            if len(summary) > 200:
                summary = summary[:197] + "..."
            result["summary"] = summary
    except (json.JSONDecodeError, UnboundLocalError):
        pass

    finished_at = datetime.now(timezone.utc).astimezone()
    result["finished_at"] = finished_at.isoformat()
    result["duration_sec"] = int((finished_at - started_at).total_seconds())

    # Save result.json
    result_path = log_dir / f"{run_id}.result.json"
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    return result


# ---------------------------------------------------------------------------
# Discord notification
# ---------------------------------------------------------------------------


def format_duration(seconds: int) -> str:
    """Format seconds into human-readable string."""
    if seconds < 60:
        return f"{seconds}s"
    minutes = seconds // 60
    secs = seconds % 60
    if secs == 0:
        return f"{minutes}m"
    return f"{minutes}m {secs}s"


def send_discord_notification(result: dict[str, Any], config: dict[str, Any]) -> None:
    """Send Discord webhook notification. Safe summary only, no raw output."""
    webhook_url = os.environ.get("CLAUDE_CRON_DISCORD_WEBHOOK", "")
    if not webhook_url:
        return

    notify_config = config.get("notify", {})
    status = result["status"]

    # Check if we should notify based on status category
    is_success = status == "success"
    is_failure = status in ("failure", "timeout", "runner_error")
    is_skip = status in ("skipped", "already_running")

    if is_success and not notify_config.get("on_success", True):
        return
    if (is_failure or is_skip) and not notify_config.get("on_failure", True):
        return

    icon = STATUS_ICONS.get(status, "❓")
    job = result["job"]
    duration = format_duration(result["duration_sec"])
    cost = f"${result['cost_usd']:.2f}" if result["cost_usd"] > 0 else ""
    model = result.get("model", "")

    # Build message parts
    parts = [duration]
    if cost:
        parts.append(cost)
    if model:
        parts.append(model)
    detail = ", ".join(parts)

    status_labels = {
        "success": "完了",
        "failure": "失敗",
        "timeout": "タイムアウト",
        "skipped": "スキップ",
        "already_running": "スキップ",
        "runner_error": "内部エラー",
    }
    label = status_labels.get(status, status)

    message = f"{icon} **{job}** {label} ({detail})"

    if status == "failure":
        message += f"\n→ exit code: {result['exit_code']}"
    elif status == "timeout":
        timeout_sec = config.get("timeout_sec", 300)
        message += f"\n→ {timeout_sec}s 上限"
    elif status == "already_running":
        message += "\n→ 前回のジョブがまだ実行中"
    elif status == "runner_error" and result.get("summary"):
        message += f"\n→ {result['summary']}"

    # Send via urllib (no external dependency)
    payload = json.dumps({"content": message}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "claude-cron-registry/1.0",
        },
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=15)
    except (urllib.error.URLError, urllib.error.HTTPError) as e:
        print(f"Warning: Discord notification failed: {e}", file=sys.stderr)


# ---------------------------------------------------------------------------
# Log cleanup
# ---------------------------------------------------------------------------


def cleanup_old_logs(job_name: str, retention_days: int) -> None:
    """Delete log and result files older than retention_days."""
    log_dir = LOGS_DIR / job_name
    if not log_dir.exists():
        return
    cutoff = time.time() - (retention_days * 86400)
    for f in log_dir.iterdir():
        if f.stat().st_mtime < cutoff:
            f.unlink()


# ---------------------------------------------------------------------------
# Crontab management
# ---------------------------------------------------------------------------


def get_current_crontab() -> str:
    """Get current crontab contents.

    Distinguishes 'no crontab for user' (empty, safe) from real errors (abort).
    """
    try:
        result = subprocess.run(
            ["crontab", "-l"],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout
        # macOS/Linux: "no crontab for <user>" on stderr when empty
        if "no crontab" in result.stderr.lower():
            return ""
        # Real error — do not silently return empty (would destroy existing entries)
        print(f"Error reading crontab: {result.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    except FileNotFoundError:
        return ""


def generate_crontab_entries(registry: dict[str, Any]) -> str:
    """Generate crontab entries from registry."""
    project_root = PROJECT_ROOT
    uv_path = shutil.which("uv")
    manage_py = CRON_DIR / "manage.py"

    lines = [
        CRONTAB_BEGIN,
        "SHELL=/bin/bash",
        f"PATH=/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:{Path.home()}/.local/bin:{Path.home()}/.cargo/bin",
    ]

    jobs = registry.get("jobs") or {}
    for job_name, job_config in sorted(jobs.items()):
        if not job_config.get("enabled", True):
            continue
        schedule = job_config["schedule"]
        cmd = f"cd {project_root} && {uv_path} run {manage_py} run {job_name} 2>> {STDERR_LOG}"
        lines.append(f"{schedule} {cmd}")

    lines.append(CRONTAB_END)
    return "\n".join(lines)


def install_crontab(registry: dict[str, Any]) -> None:
    """Install managed crontab entries, preserving user entries."""
    current = get_current_crontab()
    new_block = generate_crontab_entries(registry)

    # Remove existing managed block
    if CRONTAB_BEGIN in current:
        before = current[: current.index(CRONTAB_BEGIN)]
        after_marker = current[current.index(CRONTAB_END) + len(CRONTAB_END) :]
        current = before + after_marker

    # Append new block
    current = current.rstrip("\n")
    if current:
        current += "\n\n"
    current += new_block + "\n"

    # Install
    proc = subprocess.run(
        ["crontab", "-"],
        input=current,
        text=True,
        capture_output=True,
    )
    if proc.returncode != 0:
        print(f"Error installing crontab: {proc.stderr}", file=sys.stderr)
        sys.exit(1)


def uninstall_crontab() -> None:
    """Remove managed crontab entries."""
    current = get_current_crontab()
    if CRONTAB_BEGIN not in current:
        print("No managed crontab entries found.")
        return

    before = current[: current.index(CRONTAB_BEGIN)]
    after_marker = current[current.index(CRONTAB_END) + len(CRONTAB_END) :]
    new_content = (before + after_marker).strip("\n") + "\n"

    proc = subprocess.run(["crontab", "-"], input=new_content, text=True, capture_output=True)
    if proc.returncode != 0:
        print(f"Error removing crontab entries: {proc.stderr.strip()}", file=sys.stderr)
        sys.exit(1)
    print("Managed crontab entries removed.")


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_validate(_args: argparse.Namespace) -> None:
    """Validate registry and environment."""
    errors: list[str] = []
    warnings: list[str] = []

    # Check dependencies
    if not shutil.which("claude"):
        errors.append("claude command not found in PATH")
    if not shutil.which("uv"):
        errors.append("uv command not found in PATH")

    # Load and validate registry
    try:
        registry = load_registry()
    except Exception as e:
        errors.append(f"Failed to parse registry.yaml: {e}")
        for err in errors:
            print(f"  ERROR: {err}")
        sys.exit(1)

    jobs = registry.get("jobs") or {}
    if not jobs:
        warnings.append("No jobs defined in registry")

    for name, config in jobs.items():
        if not validate_job_name(name):
            errors.append(f"Invalid job name '{name}': must match [a-z0-9-]")
        if "schedule" not in config:
            errors.append(f"Job '{name}': missing 'schedule'")
        elif not validate_schedule(config["schedule"]):
            errors.append(f"Job '{name}': invalid cron schedule '{config['schedule']}'")
        if "prompt" not in config:
            errors.append(f"Job '{name}': missing 'prompt'")

    # Check .env
    if not ENV_PATH.exists():
        warnings.append(f".env file not found at {ENV_PATH}")
    else:
        load_env_file()
        if not os.environ.get("CLAUDE_CRON_DISCORD_WEBHOOK"):
            warnings.append("CLAUDE_CRON_DISCORD_WEBHOOK not set in .env")

    # Ensure directories
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)

    # Print results
    print("Claude Cron Registry — Validate")
    print("=" * 40)

    if errors:
        for err in errors:
            print(f"  ERROR: {err}")
        sys.exit(1)

    if warnings:
        for warn in warnings:
            print(f"  WARN: {warn}")

    enabled = sum(1 for c in jobs.values() if c.get("enabled", True))
    print(f"  Jobs: {len(jobs)} total, {enabled} enabled")
    print(f"  claude: {shutil.which('claude')}")
    print(f"  uv: {shutil.which('uv')}")
    print("  OK")


def cmd_run(args: argparse.Namespace) -> None:
    """Run a single job."""
    job_name = args.job
    load_env_file()
    registry = load_registry()
    config = get_job_config(registry, job_name)

    if not validate_job_name(job_name):
        print(f"Error: invalid job name '{job_name}'", file=sys.stderr)
        sys.exit(1)

    # Check enabled
    if not config.get("enabled", True):
        now = datetime.now(timezone.utc).astimezone()
        result = {
            "run_id": now.strftime("%Y%m%d-%H%M%S"),
            "job": job_name,
            "status": "skipped",
            "exit_code": 0,
            "started_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_sec": 0,
            "cost_usd": 0.0,
            "tokens": {"input": 0, "output": 0},
            "model": config.get("model", ""),
            "log_path": "",
            "summary": "Job disabled",
        }
        send_discord_notification(result, config)
        print(f"Job '{job_name}' is disabled, skipping.")
        return

    # Acquire lock
    lock_fd = acquire_lock(job_name)
    if lock_fd is None:
        now = datetime.now(timezone.utc).astimezone()
        result = {
            "run_id": now.strftime("%Y%m%d-%H%M%S"),
            "job": job_name,
            "status": "already_running",
            "exit_code": 0,
            "started_at": now.isoformat(),
            "finished_at": now.isoformat(),
            "duration_sec": 0,
            "cost_usd": 0.0,
            "tokens": {"input": 0, "output": 0},
            "model": config.get("model", ""),
            "log_path": "",
            "summary": "Previous run still in progress",
        }

        # Save result.json for already_running too
        log_dir = LOGS_DIR / job_name
        log_dir.mkdir(parents=True, exist_ok=True)
        result_path = log_dir / f"{result['run_id']}.result.json"
        result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

        send_discord_notification(result, config)
        print(f"Job '{job_name}' is already running, skipping.")
        return

    try:
        # Run claude
        result = run_claude(config, job_name)

        # Notify
        send_discord_notification(result, config)

        # Cleanup old logs
        retention = config.get("log_retention_days", 14)
        cleanup_old_logs(job_name, retention)

        # Print summary
        icon = STATUS_ICONS.get(result["status"], "?")
        duration = format_duration(result["duration_sec"])
        cost = f"${result['cost_usd']:.2f}"
        print(f"{icon} {job_name}: {result['status']} ({duration}, {cost})")

    finally:
        os.close(lock_fd)


def cmd_install(_args: argparse.Namespace) -> None:
    """Install crontab entries from registry."""
    registry = load_registry()

    # Validate first
    print("Validating registry...")
    jobs = registry.get("jobs") or {}
    for name, config in jobs.items():
        if not validate_job_name(name):
            print(f"Error: invalid job name '{name}'", file=sys.stderr)
            sys.exit(1)
        if "schedule" not in config:
            print(f"Error: job '{name}' missing schedule", file=sys.stderr)
            sys.exit(1)
        if not validate_schedule(config["schedule"]):
            print(f"Error: job '{name}' invalid cron schedule '{config['schedule']}'", file=sys.stderr)
            sys.exit(1)

    if not shutil.which("claude"):
        print("Error: claude not found in PATH", file=sys.stderr)
        sys.exit(1)
    if not shutil.which("uv"):
        print("Error: uv not found in PATH", file=sys.stderr)
        sys.exit(1)

    # Ensure directories
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    LOCKS_DIR.mkdir(parents=True, exist_ok=True)

    install_crontab(registry)

    enabled = [n for n, c in jobs.items() if c.get("enabled", True)]
    disabled = [n for n, c in jobs.items() if not c.get("enabled", True)]

    print(f"\nInstalled {len(enabled)} job(s) to crontab:")
    for name in enabled:
        print(f"  + {name}  [{jobs[name]['schedule']}]")
    if disabled:
        print(f"\nSkipped {len(disabled)} disabled job(s):")
        for name in disabled:
            print(f"  - {name}")


def cmd_uninstall(_args: argparse.Namespace) -> None:
    """Remove managed crontab entries."""
    uninstall_crontab()


def cmd_status(_args: argparse.Namespace) -> None:
    """Show status of all jobs."""
    registry = load_registry()
    jobs = registry.get("jobs") or {}

    print("Claude Cron Registry — Status")
    print("=" * 40)

    if not jobs:
        print("  No jobs defined.")
        return

    for name, config in sorted(jobs.items()):
        enabled = config.get("enabled", True)
        schedule = config.get("schedule", "?")
        state = "enabled" if enabled else "disabled"
        description = config.get("description", "")

        print(f"\n{name}  [{state}]  {schedule}")
        if description:
            print(f"  {description}")

        # Show recent results
        log_dir = LOGS_DIR / name
        if not log_dir.exists():
            print("  No runs yet.")
            continue

        results = sorted(log_dir.glob("*.result.json"), reverse=True)[:5]
        if not results:
            print("  No runs yet.")
            continue

        print(f"  Last {len(results)} run(s):")
        for result_path in results:
            try:
                data = json.loads(result_path.read_text(encoding="utf-8"))
                icon = STATUS_ICONS.get(data["status"], "?")
                ts = data.get("started_at", "")[:16].replace("T", " ")
                dur = f"{data.get('duration_sec', 0)}s"
                cost = f"${data.get('cost_usd', 0):.2f}"
                status = data.get("status", "?")
                print(f"    {icon} {ts}  {dur:>6}  {cost:>6}  {status}")
            except (json.JSONDecodeError, KeyError):
                print(f"    ? {result_path.name} (corrupt)")


def cmd_enable(args: argparse.Namespace) -> None:
    """Enable a job and reinstall crontab."""
    _toggle_job(args.job, enabled=True)


def cmd_disable(args: argparse.Namespace) -> None:
    """Disable a job and reinstall crontab."""
    _toggle_job(args.job, enabled=False)


def _find_jobs_section_start(lines: list[str]) -> int | None:
    """Find the line index of the top-level 'jobs:' key."""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)
        if current_indent == 0 and (stripped == "jobs:" or stripped.startswith("jobs:")):
            return i
    return None


def _find_job_block(lines: list[str], job_name: str) -> tuple[int, int] | None:
    """Find start and end line indices of a job block within the jobs: section.

    Only searches within the top-level 'jobs:' section to avoid matching
    keys in other sections (e.g. defaults.notify vs a job named 'notify').
    Comment lines are ignored for block boundary detection.

    Returns (start, end) where end is exclusive, or None if not found.
    """
    jobs_start = _find_jobs_section_start(lines)
    if jobs_start is None:
        return None

    job_start = None
    job_indent = 0

    for i in range(jobs_start + 1, len(lines)):
        line = lines[i]
        stripped = line.lstrip()
        current_indent = len(line) - len(stripped)

        # Skip empty lines and comments
        if not stripped or stripped.startswith("#"):
            continue

        # Left the jobs: section entirely (another top-level key)
        if current_indent == 0:
            break

        if job_start is None:
            # Looking for the job name at the job-name indent level
            if stripped == f"{job_name}:" or stripped.startswith(f"{job_name}:"):
                job_start = i
                job_indent = current_indent
        else:
            # Inside the job block — check if we've left it
            if current_indent <= job_indent:
                return (job_start, i)

    if job_start is not None:
        return (job_start, len(lines))
    return None


def _toggle_job(job_name: str, *, enabled: bool) -> None:
    """Toggle a job's enabled state in registry.yaml and reinstall."""
    registry = load_registry()
    jobs = registry.get("jobs") or {}

    if job_name not in jobs:
        print(f"Error: job '{job_name}' not found", file=sys.stderr)
        sys.exit(1)

    content = REGISTRY_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    block = _find_job_block(lines, job_name)
    if block is None:
        print(f"Error: job '{job_name}' not found in YAML", file=sys.stderr)
        sys.exit(1)

    job_start, job_end = block
    modified = False

    for i in range(job_start + 1, job_end):
        stripped = lines[i].lstrip()
        current_indent = len(lines[i]) - len(stripped)
        if stripped.startswith("enabled:"):
            lines[i] = f"{' ' * current_indent}enabled: {'true' if enabled else 'false'}"
            modified = True
            break

    if not modified:
        print(f"Warning: 'enabled' field not found for job '{job_name}', adding it", file=sys.stderr)
        job_line = lines[job_start]
        indent = len(job_line) - len(job_line.lstrip()) + 2
        lines.insert(job_start + 1, f"{' ' * indent}enabled: {'true' if enabled else 'false'}")

    REGISTRY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")

    state = "enabled" if enabled else "disabled"
    print(f"Job '{job_name}' {state}.")

    # Reinstall crontab
    registry = load_registry()
    install_crontab(registry)
    print("Crontab updated.")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a job from the registry and reinstall crontab."""
    _delete_job(args.job)


def _delete_job(job_name: str) -> None:
    """Remove a job from registry.yaml and reinstall crontab."""
    registry = load_registry()
    jobs = registry.get("jobs") or {}

    if job_name not in jobs:
        print(f"Error: job '{job_name}' not found", file=sys.stderr)
        sys.exit(1)

    content = REGISTRY_PATH.read_text(encoding="utf-8")
    lines = content.splitlines()

    block = _find_job_block(lines, job_name)
    if block is None:
        print(f"Error: job '{job_name}' not found in YAML", file=sys.stderr)
        sys.exit(1)

    job_start, job_end = block

    # Also remove blank lines immediately before the job block
    while job_start > 0 and not lines[job_start - 1].strip():
        job_start -= 1

    del lines[job_start:job_end]

    REGISTRY_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Job '{job_name}' deleted from registry.")

    # Reinstall crontab
    registry = load_registry()
    install_crontab(registry)
    print("Crontab updated.")


def cmd_logs(args: argparse.Namespace) -> None:
    """Show recent logs for a job."""
    job_name = args.job
    count = args.n

    log_dir = LOGS_DIR / job_name
    if not log_dir.exists():
        print(f"No logs for job '{job_name}'.")
        return

    log_files = sorted(log_dir.glob("*.log"), reverse=True)[:count]
    if not log_files:
        print(f"No log files for job '{job_name}'.")
        return

    for log_file in reversed(log_files):  # Show oldest first
        result_file = log_file.with_suffix(".result.json")
        print(f"\n{'=' * 60}")
        print(f"Log: {log_file.name}")

        if result_file.exists():
            try:
                data = json.loads(result_file.read_text(encoding="utf-8"))
                icon = STATUS_ICONS.get(data["status"], "?")
                print(f"Status: {icon} {data['status']} | Duration: {data.get('duration_sec', '?')}s | Cost: ${data.get('cost_usd', 0):.2f}")
            except (json.JSONDecodeError, KeyError):
                pass

        print("-" * 60)
        content = log_file.read_text(encoding="utf-8")
        # Show last 50 lines to avoid flooding terminal
        lines = content.splitlines()
        if len(lines) > 50:
            print(f"... ({len(lines) - 50} lines omitted)")
            print("\n".join(lines[-50:]))
        else:
            print(content)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Claude Cron Registry Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subparsers.add_parser("run", help="Run a job")
    p_run.add_argument("job", help="Job name")
    p_run.set_defaults(func=cmd_run)

    # install
    p_install = subparsers.add_parser("install", help="Install crontab entries")
    p_install.set_defaults(func=cmd_install)

    # uninstall
    p_uninstall = subparsers.add_parser("uninstall", help="Remove crontab entries")
    p_uninstall.set_defaults(func=cmd_uninstall)

    # status
    p_status = subparsers.add_parser("status", help="Show job status")
    p_status.set_defaults(func=cmd_status)

    # validate
    p_validate = subparsers.add_parser("validate", help="Validate registry")
    p_validate.set_defaults(func=cmd_validate)

    # enable
    p_enable = subparsers.add_parser("enable", help="Enable a job")
    p_enable.add_argument("job", help="Job name")
    p_enable.set_defaults(func=cmd_enable)

    # disable
    p_disable = subparsers.add_parser("disable", help="Disable a job")
    p_disable.add_argument("job", help="Job name")
    p_disable.set_defaults(func=cmd_disable)

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a job from registry")
    p_delete.add_argument("job", help="Job name")
    p_delete.set_defaults(func=cmd_delete)

    # logs
    p_logs = subparsers.add_parser("logs", help="Show recent logs")
    p_logs.add_argument("job", help="Job name")
    p_logs.add_argument("-n", type=int, default=3, help="Number of recent logs (default: 3)")
    p_logs.set_defaults(func=cmd_logs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
