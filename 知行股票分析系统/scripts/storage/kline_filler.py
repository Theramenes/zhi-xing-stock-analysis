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

    # 快速路径：DB 已满足
    candles = db.get_candles(code, required_days)
    if len(candles) >= required_days:
        return candles

    # 委托 Coordinator
    from data_source.kline_coordinator import get_coordinator
    coordinator = get_coordinator()
    result, source = coordinator.fetch_kline(code, required_trading_days=required_days)
    if result:
        return result

    # 全部失败，返回 DB 现有数据
    return candles
