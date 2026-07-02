from __future__ import annotations

from dataclasses import dataclass

from app.db.models import AcquisitionTask


TASK_PRIORITY = {
    "DAILY_PRICES": 10,
    "FUNDAMENTALS": 20,
    "DIVIDENDS": 30,
    "SPLITS": 40,
    "CORPORATE_ACTIONS": 50,
    "FINANCIAL_STATEMENTS": 60,
    "EARNINGS": 70,
    "OPTIONS_CONTRACTS": 80,
    "OPTIONS_AGGREGATES": 90,
    "OPTIONS_TRADES": 100,
    "OPTIONS_QUOTES": 110,
}


@dataclass(frozen=True)
class QueueItem:
    task_id: int
    job_id: int
    task_type: str
    ticker: str | None
    priority: int


def build_queue(tasks: list[AcquisitionTask]) -> list[QueueItem]:
    ordered = sorted(
        tasks,
        key=lambda task: (
            TASK_PRIORITY.get(task.task_type, 999),
            task.ticker or "",
            task.id or 0,
        ),
    )
    return [
        QueueItem(
            task_id=task.id or 0,
            job_id=task.job_id,
            task_type=task.task_type,
            ticker=task.ticker,
            priority=TASK_PRIORITY.get(task.task_type, 999),
        )
        for task in ordered
    ]
