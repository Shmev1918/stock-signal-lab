from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "stock-signal-lab"
    database_url: str = "postgresql+psycopg://stock:stock@localhost:5432/stock_signal_lab"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    market_data_provider: str = "mock"
    scoring_strategy: str = "balanced"
    polygon_api_key: str | None = None
    polygon_rate_limit_per_minute: int = 3
    polygon_mode: str = "free"
    polygon_historical_years: int = 2
    default_watchlist: list[str] = Field(
        default_factory=lambda: [
            "AAPL",
            "MSFT",
            "GOOGL",
            "AMZN",
            "NVDA",
            "META",
            "TSLA",
            "BRK.B",
            "V",
            "JNJ",
            "KO",
            "PEP",
            "COST",
            "PLTR",
            "SOFI",
            "RIVN",
        ]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
