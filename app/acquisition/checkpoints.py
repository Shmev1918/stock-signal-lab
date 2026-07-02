from __future__ import annotations

from datetime import date

from app.db.models import AcquisitionTask


def task_request_key(job_id: int, task: AcquisitionTask, *, force: bool = False) -> str:
    parts = [str(job_id), str(task.id or "task"), task.task_type, task.ticker or "all"]
    if task.start_date:
        parts.append(task.start_date.isoformat())
    if task.end_date:
        parts.append(task.end_date.isoformat())
    if force:
        parts.append("force")
    return ":".join(parts)


def task_is_runnable(task: AcquisitionTask, *, force: bool = False) -> bool:
    if force:
        return task.status != "RUNNING"
    return task.status == "PENDING"


def task_was_completed(task: AcquisitionTask) -> bool:
    return task.status == "COMPLETED"


def task_date_window(task: AcquisitionTask, fallback_start: date | None = None, fallback_end: date | None = None) -> tuple[date | None, date | None]:
    return task.start_date or fallback_start, task.end_date or fallback_end
