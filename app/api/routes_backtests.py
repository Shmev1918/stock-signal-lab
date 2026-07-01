from datetime import date

from fastapi import APIRouter, Depends
from sqlmodel import Session

from app.backtesting.runner import BacktestRequest, run_backtest
from app.db.session import get_session

router = APIRouter()


@router.post("/backtests/run")
def run_backtests(session: Session = Depends(get_session)):
    request = BacktestRequest(name="default", start_date=date.today(), end_date=date.today())
    return run_backtest(session, request)


@router.get("/backtests")
def list_backtests():
    return []


@router.get("/backtests/{backtest_id}")
def get_backtest(backtest_id: int):
    return {"id": backtest_id}
