from __future__ import annotations

from collections import Counter
from typing import Any

from sqlmodel import Session, select

from app.db.models import AcquisitionJob, AcquisitionTask


def build_job_report(session: Session, job_id: int) -> dict[str, Any]:
    job = session.get(AcquisitionJob, job_id)
    if job is None:
        raise LookupError(f"Acquisition job not found: {job_id}")
    tasks = list(session.exec(select(AcquisitionTask).where(AcquisitionTask.job_id == job_id)))
    counts = Counter(task.status for task in tasks)
    failures = [
        {
            "task_id": task.id,
            "task_type": task.task_type,
            "ticker": task.ticker,
            "status": task.status,
            "last_error": task.last_error,
            "rows_imported": task.rows_imported,
        }
        for task in tasks
        if task.status == "FAILED"
    ]
    progress = round((counts.get("COMPLETED", 0) + counts.get("SKIPPED", 0)) / max(len(tasks), 1) * 100.0, 1)
    return {
        "job": job.model_dump(),
        "task_total": len(tasks),
        "task_counts": dict(counts),
        "progress_percent": progress,
        "failed_tasks": failures,
        "tasks": [task.model_dump() for task in tasks],
    }
