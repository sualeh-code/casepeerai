"""
Workflow Scheduler - Background scheduler for daily automated tasks.

Runs alongside the Gmail poller and executes:
- Case checker (scan for new cases)
- Follow-up reminders (check for unresponsive providers)
- Any other scheduled workflows

Same asyncio background task pattern as gmail_poller.py.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Optional, Dict, Any, List

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# State tracking
# ---------------------------------------------------------------------------

_scheduler_running = False
_scheduler_task: Optional[asyncio.Task] = None
_scheduler_stats = {
    "started_at": None,
    "last_run": None,
    "runs_completed": 0,
    "errors": 0,
    "last_error": None,
    "status": "stopped",
}

# Default schedule: run daily tasks every 24 hours (86400 seconds)
SCHEDULE_INTERVAL_SECONDS = 86400
# Initial delay after startup before first run (5 minutes)
INITIAL_DELAY_SECONDS = 300
# Session keep-alive interval (20 minutes) to prevent CasePeer session expiry
KEEPALIVE_INTERVAL_SECONDS = 1200


def get_scheduler_stats() -> Dict[str, Any]:
    """Return current scheduler status and stats."""
    return {**_scheduler_stats, "running": _scheduler_running}


# ---------------------------------------------------------------------------
# Workflow run tracking in Turso
# ---------------------------------------------------------------------------

def _log_workflow_start(workflow_name: str, case_id: str = "", triggered_by: str = "scheduler") -> Optional[int]:
    """Log a workflow run start and return the run ID."""
    from turso_client import turso
    try:
        turso.execute(
            "INSERT INTO workflow_runs (workflow_name, case_id, status, triggered_by) VALUES (?, ?, 'running', ?)",
            [workflow_name, case_id, triggered_by]
        )
        # Get the last inserted ID
        row = turso.fetch_one("SELECT MAX(id) as id FROM workflow_runs WHERE workflow_name = ? AND case_id = ?",
                              [workflow_name, case_id])
        return row["id"] if row else None
    except Exception as e:
        logger.error(f"[Scheduler] Failed to log workflow start: {e}")
        return None


def _log_workflow_end(run_id: int, status: str = "completed", result: Dict = None, error: str = ""):
    """Update a workflow run with completion status."""
    from turso_client import turso
    try:
        turso.execute(
            "UPDATE workflow_runs SET status = ?, completed_at = datetime('now'), result_json = ?, error = ? WHERE id = ?",
            [status, json.dumps(result or {}), error, run_id]
        )
    except Exception as e:
        logger.error(f"[Scheduler] Failed to log workflow end: {e}")


def get_workflow_runs(limit: int = 50, workflow_name: str = "") -> List[Dict]:
    """Get recent workflow runs."""
    from turso_client import turso
    try:
        if workflow_name:
            return turso.fetch_all(
                "SELECT * FROM workflow_runs WHERE workflow_name = ? ORDER BY started_at DESC LIMIT ?",
                [workflow_name, limit]
            )
        return turso.fetch_all(
            "SELECT * FROM workflow_runs ORDER BY started_at DESC LIMIT ?",
            [limit]
        )
    except Exception as e:
        logger.error(f"[Scheduler] Failed to get workflow runs: {e}")
        return []


# ---------------------------------------------------------------------------
# Daily task runner
# ---------------------------------------------------------------------------

async def _run_daily_tasks():
    """Execute all enabled daily tasks."""
    from turso_client import get_setting

    # Task 1: Case Checker
    case_checker_enabled = (get_setting("case_checker_enabled", "true") or "").lower() == "true"
    if case_checker_enabled:
        await _run_task("case_checker", _run_case_checker)

    # Task 2: Follow-up Reminders
    followup_enabled = (get_setting("followup_reminders_enabled", "true") or "").lower() == "true"
    if followup_enabled:
        await _run_task("followup_reminders", _run_followup_reminders)


async def _run_task(name: str, func):
    """Run a single task with logging and error handling."""
    run_id = _log_workflow_start(name)
    try:
        logger.info(f"[Scheduler] Starting task: {name}")
        result = await func()
        _log_workflow_end(run_id, "completed", result)
        logger.info(f"[Scheduler] Task {name} completed: {result}")
    except Exception as e:
        logger.error(f"[Scheduler] Task {name} failed: {e}", exc_info=True)
        _log_workflow_end(run_id, "failed", error=str(e))
        _scheduler_stats["errors"] += 1
        _scheduler_stats["last_error"] = f"{datetime.now().isoformat()}: {name}: {str(e)[:200]}"


async def _run_case_checker() -> Dict:
    """Run the case checker workflow."""
    try:
        from wf_case_checker import run_case_checker
        return await run_case_checker()
    except ImportError:
        logger.warning("[Scheduler] wf_case_checker not available yet")
        return {"skipped": True, "reason": "module not available"}


async def _run_followup_reminders() -> Dict:
    """Run the follow-up reminders workflow."""
    try:
        from wf_followup import run_followup_reminders
        return await run_followup_reminders()
    except ImportError:
        logger.warning("[Scheduler] wf_followup not available yet")
        return {"skipped": True, "reason": "module not available"}


# ---------------------------------------------------------------------------
# Manual workflow triggers
# ---------------------------------------------------------------------------

async def trigger_workflow(workflow_name: str, case_id: str = "",
                           triggered_by: str = "manual") -> Dict:
    """Trigger a specific workflow manually. Returns immediately, runs in background."""
    run_id = _log_workflow_start(workflow_name, case_id, triggered_by)

    async def _execute():
        try:
            if workflow_name == "initial_negotiation":
                from wf_initial_negotiation import run_initial_negotiation
                result = await run_initial_negotiation(case_id)
            elif workflow_name == "case_checker":
                from wf_case_checker import run_case_checker
                result = await run_case_checker()
            elif workflow_name == "classification":
                from wf_classification import run_classification
                result = await run_classification(case_id)
            elif workflow_name == "followup":
                from wf_followup import run_followup_reminders
                result = await run_followup_reminders()
            elif workflow_name == "thirdparty":
                from wf_thirdparty import run_thirdparty_processing
                result = await run_thirdparty_processing(case_id)
            elif workflow_name == "get_mail_sub":
                from wf_get_mail_sub import run_get_mail_sub
                result = await run_get_mail_sub(case_id)
            else:
                result = {"error": f"Unknown workflow: {workflow_name}"}
                _log_workflow_end(run_id, "failed", error=f"Unknown workflow: {workflow_name}")
                return
            _log_workflow_end(run_id, "completed", result)
        except Exception as e:
            logger.error(f"[Scheduler] Workflow {workflow_name} failed: {e}", exc_info=True)
            _log_workflow_end(run_id, "failed", error=str(e))

    asyncio.create_task(_execute())
    return {"status": "triggered", "run_id": run_id, "workflow": workflow_name, "case_id": case_id}


# ---------------------------------------------------------------------------
# Scheduler loop
# ---------------------------------------------------------------------------

_keepalive_task: Optional[asyncio.Task] = None
_keepalive_running = False


async def _keepalive_loop():
    """Ping CasePeer every 20 minutes to prevent session expiry."""
    global _keepalive_running
    _keepalive_running = True
    logger.info(f"[Keepalive] Started. Pinging every {KEEPALIVE_INTERVAL_SECONDS}s")
    while _keepalive_running:
        try:
            await asyncio.sleep(KEEPALIVE_INTERVAL_SECONDS)
            if not _keepalive_running:
                break
            # Make a lightweight GET to CasePeer dashboard to refresh the session
            from casepeer_helpers import casepeer_get_raw
            resp = await asyncio.to_thread(casepeer_get_raw, "/law/dashboard/")
            if resp and resp.status_code == 200:
                logger.debug("[Keepalive] CasePeer session refreshed")
            else:
                status = resp.status_code if resp else "no response"
                logger.warning(f"[Keepalive] CasePeer ping returned {status}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.warning(f"[Keepalive] Ping failed: {e}")
    _keepalive_running = False


async def start_keepalive():
    """Start the session keepalive independently (always runs)."""
    global _keepalive_task, _keepalive_running
    if _keepalive_running:
        return {"status": "already_running"}
    _keepalive_task = asyncio.create_task(_keepalive_loop())
    return {"status": "started"}


async def _scheduler_loop():
    """Background loop that runs daily tasks."""
    global _scheduler_running, _scheduler_stats

    _scheduler_stats["started_at"] = datetime.now().isoformat()
    _scheduler_stats["status"] = "running"

    logger.info(f"[Scheduler] Started. Initial delay: {INITIAL_DELAY_SECONDS}s, Interval: {SCHEDULE_INTERVAL_SECONDS}s")

    # Initial delay
    try:
        await asyncio.sleep(INITIAL_DELAY_SECONDS)
    except asyncio.CancelledError:
        _scheduler_stats["status"] = "stopped"
        return

    while _scheduler_running:
        try:
            _scheduler_stats["last_run"] = datetime.now().isoformat()
            _scheduler_stats["status"] = "running tasks"

            await _run_daily_tasks()

            _scheduler_stats["runs_completed"] += 1
            _scheduler_stats["status"] = "idle (waiting for next cycle)"

        except Exception as e:
            _scheduler_stats["errors"] += 1
            _scheduler_stats["last_error"] = f"{datetime.now().isoformat()}: {str(e)[:200]}"
            _scheduler_stats["status"] = f"error: {str(e)[:100]}"
            logger.error(f"[Scheduler] Cycle error: {e}", exc_info=True)

        try:
            await asyncio.sleep(SCHEDULE_INTERVAL_SECONDS)
        except asyncio.CancelledError:
            logger.info("[Scheduler] Sleep cancelled, shutting down")
            break

    _scheduler_stats["status"] = "stopped"
    logger.info("[Scheduler] Stopped")


# ---------------------------------------------------------------------------
# Start / Stop controls
# ---------------------------------------------------------------------------

async def start_scheduler():
    """Start the background scheduler for daily tasks."""
    global _scheduler_running, _scheduler_task

    if _scheduler_running:
        logger.info("[Scheduler] Already running")
        return {"status": "already_running"}

    _scheduler_running = True
    _scheduler_task = asyncio.create_task(_scheduler_loop())
    logger.info("[Scheduler] Starting background scheduler")
    return {"status": "started"}


async def stop_scheduler():
    """Stop the background scheduler."""
    global _scheduler_running, _scheduler_task

    if not _scheduler_running:
        return {"status": "already_stopped"}

    _scheduler_running = False
    if _scheduler_task:
        _scheduler_task.cancel()
        _scheduler_task = None

    _scheduler_stats["status"] = "stopped"
    logger.info("[Scheduler] Stop requested")
    return {"status": "stopped"}
