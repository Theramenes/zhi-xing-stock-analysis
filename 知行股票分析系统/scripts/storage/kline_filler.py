"""
K线按需填充器 — 总是先查 DB，不够再用多源级联补

核心逻辑:
  ensure_candles(code) → 查 DB → 算缺口 → KlineCascade 多源降级补 → 返回 candles
"""
import sys
import os
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .db import get_db


def ensure_candles(code: str, required_days: int = 114) -> List[dict]:
    """
    确保某只股票有足够 K 线数据。不够则走多源级联自动补缺。

    Args:
        code: 股票代码 (如 300083)
        required_days: 最少需要多少交易日数据（B1需要114）

    Returns:
        candles 列表 [{date, open, high, low, close, volume}, ...]，按日期升序
    """
    db = get_db()

    # 1. 查 DB
    candles = db.get_candles(code, required_days)
    if len(candles) >= required_days:
        return candles

    # 2. 从本地交易日历精确取最近 required_days 个交易日算缺口
    end = datetime.now().strftime("%Y-%m-%d")
    db.ensure_trading_calendar(end=end)
    all_days = db.get_trading_days("2020-01-01", end)
    if len(all_days) < required_days:
        print(f"  [filler] 交易日历不足 {required_days} 天，返回现有 {len(candles)} 天")
        return candles
    trading_days = all_days[-required_days:]

    missing = db.get_missing_dates(code, trading_days)
    if not missing:
        return candles

    print(f"  [filler] {code}: DB有{len(candles)}天, 补最近{len(missing)}天...")

    # 3. 走多源级联补缺口
    from data_source.kline_cascade import get_cascade
    cascade = get_cascade()

    start_date = missing[0]
    end_date = missing[-1]
    new_candles, source = cascade.get_kline_range(code, start_date, end_date)
    if new_candles:
        n = db.upsert_candles(code, new_candles)
        print(f"  [filler] {code}: [{source}] 拉取{len(new_candles)}条, 写入{n}条")
    else:
        print(f"  [filler] {code}: 所有数据源失败，K线不足")

    return db.get_candles(code, required_days)
