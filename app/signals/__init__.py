from __future__ import annotations

from app.signals.base import SignalRecord as SignalRecord

__all__ = ["SignalRecord", "SignalEngine"]


def __getattr__(name: str):
    if name == "SignalEngine":
        from app.signals.signal_engine import SignalEngine

        return SignalEngine
    raise AttributeError(name)
