"""Scheduler bootstrap for registered jobs."""

from __future__ import annotations

import logging
import time
from typing import Any

from apscheduler.schedulers.background import BackgroundScheduler

from app.jobs.registry import list_job_definitions, run_registered_jobs_for_accounts


def build_scheduler(
    *,
    interval_seconds: int | None = None,
) -> BackgroundScheduler:
    """Build APScheduler with all registered jobs."""
    scheduler = BackgroundScheduler(timezone="UTC")

    for definition in list_job_definitions():
        seconds = interval_seconds or definition.default_interval_seconds
        scheduler.add_job(
            run_registered_jobs_for_accounts,
            trigger="interval",
            seconds=seconds,
            id=f"job:{definition.name}",
            replace_existing=True,
            max_instances=1,
            coalesce=True,
            kwargs={
                "job_name": definition.name,
                "trigger_source": "scheduler",
            },
        )

    return scheduler


def run_scheduler_loop(
    *,
    interval_seconds: int | None = None,
    duration_seconds: int | None = None,
) -> dict[str, Any]:
    """Run scheduler until interrupted or until duration elapses."""
    logger = logging.getLogger(__name__)
    scheduler = build_scheduler(interval_seconds=interval_seconds)
    registered_jobs = [job.id for job in scheduler.get_jobs()]

    logger.info(
        "Scheduler bootstrap complete",
        extra={
            "module_name": "module0",
            "status": "started",
            "trigger_source": "scheduler",
            "registered_jobs": registered_jobs,
            "interval_seconds": interval_seconds,
            "duration_seconds": duration_seconds,
        },
    )

    scheduler.start()
    try:
        if duration_seconds is None:
            while True:
                time.sleep(1)
        else:
            time.sleep(duration_seconds)
    except KeyboardInterrupt:
        logger.info(
            "Scheduler interrupted by user",
            extra={
                "module_name": "module0",
                "status": "interrupted",
                "trigger_source": "scheduler",
            },
        )
    finally:
        scheduler.shutdown(wait=False)
        logger.info(
            "Scheduler stopped",
            extra={
                "module_name": "module0",
                "status": "stopped",
                "trigger_source": "scheduler",
                "registered_jobs": registered_jobs,
            },
        )

    return {
        "status": "ok",
        "registered_jobs": registered_jobs,
        "interval_seconds": interval_seconds,
        "duration_seconds": duration_seconds,
    }
