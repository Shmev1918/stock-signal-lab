from __future__ import annotations

from sqlmodel import Session, select

from app.db.models import WatchlistItem
from app.db.session import engine


def test_database_session_works() -> None:
    with Session(engine) as session:
        session.add(WatchlistItem(ticker="AAPL"))
        session.commit()
        found = session.exec(select(WatchlistItem).where(WatchlistItem.ticker == "AAPL")).first()
        assert found is not None
        assert found.ticker == "AAPL"

