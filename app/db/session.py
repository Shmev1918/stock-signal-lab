from collections.abc import Iterator
from pathlib import Path

from sqlmodel import Session, SQLModel, create_engine

from app.config import get_settings

settings = get_settings()

engine_kwargs: dict[str, object] = {"echo": False}
if settings.database_url.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
    if settings.database_url == "sqlite:///./stock_signal_lab.db":
        Path("stock_signal_lab.db").touch(exist_ok=True)

engine = create_engine(settings.database_url, **engine_kwargs)


def init_db() -> None:
    if settings.database_url.startswith("sqlite"):
        SQLModel.metadata.create_all(engine)


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
