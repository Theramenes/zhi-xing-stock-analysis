"""
K线按需填充器 — 委托 KlineFetchCoordinator

Coordinator 内部自动处理:
  - 交易日历更新 (三级降级)
  - 起始日期计算 (交易日反推)
  - 多源级联 (iFind 快速路径 + 免费源带熔断)
  - 迭代补缺 (不足时自动往前补)
  - SQLite 写入
"""
from typing import List

from .db import get_db


def ensure_candles(code: str, required_days: int = 114) -> List[dict]:
    """确保某只股票有足够 K 线数据。

    Args:
        code: 股票代码
        required_days: 最少需要多少交易日数据（B1需要114）
    """
    db = get_db()

    candles = db.get_candles(code, required_days)

    # 缓存有效：条数够 + 覆盖到最近交易日（不是 date.today()，盘中无新数据）
    cached_max = max(c["date"] for c in candles) if candles else ""
    latest_td = db.conn.execute(
        "SELECT MAX(date) FROM trading_calendar WHERE date <= date('now')"
    ).fetchone()[0]
    if len(candles) >= required_days and cached_max >= latest_td:
        return candles

    # 委托 Coordinator — 内部自动补缺到最新
    from data_source.kline_coordinator import get_coordinator
    coordinator = get_coordinator()
    result, source = coordinator.fetch_kline(code, required_trading_days=required_days)
    if result:
        return result

    return candles
