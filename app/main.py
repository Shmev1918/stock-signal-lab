from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_analysis import router as analysis_router
from app.api.routes_backtests import router as backtest_router
from app.api.routes_experiments import router as experiments_router
from app.api.routes_decisions import router as decisions_router
from app.api.routes_export import router as export_router
from app.api.routes_health import router as health_router
from app.api.routes_scores import router as scores_router
from app.api.routes_signals import router as signals_router
from app.api.routes_stocks import router as stocks_router
from app.api.routes_watchlist import router as watchlist_router
from app.db.session import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield


app = FastAPI(title="stock-signal-lab", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
        "http://127.0.0.1:4173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


app.include_router(health_router)
app.include_router(watchlist_router)
app.include_router(stocks_router)
app.include_router(scores_router)
app.include_router(signals_router)
app.include_router(analysis_router)
app.include_router(decisions_router)
app.include_router(export_router)
app.include_router(backtest_router)
app.include_router(experiments_router)
