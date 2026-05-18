"""
K线按需填充器 — 总是先查 DB，不够再拉

核心逻辑:
  ensure_candles(code) → 查 DB → 算缺口 → 四源降级补 → 返回 candles
"""
import sys
import os
from datetime import datetime
from typing import List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .db import get_db


def ensure_candles(code: str, required_days: int = 114) -> List[dict]:
    """
    确保某只股票有足够 K 线数据。不够则自动补缺。

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

    # 2. 算缺口
    today = datetime.now().strftime("%Y-%m-%d")
    trading_days = _get_trading_days("2025-01-01", today)
    if not trading_days:
        print(f"  [filler] 无法获取交易日历，返回现有 {len(candles)} 天")
        return candles

    missing = db.get_missing_dates(code, trading_days[-required_days * 2:])
    if not missing:
        return candles

    print(f"  [filler] {code}: DB有{len(candles)}天, 缺{len(missing)}天, 补缺中...")

    # 3. 四源降级补缺（按日期分组，减少 API 调用）
    from data_source.ifind_client import IFindClient
    from data_source.config import config

    client = IFindClient()
    filled = 0

    # 合并连续日期为一次请求
    batches = _batch_dates(missing)
    for start_d, end_d in batches:
        resp = client.get_kline_range(code, start_d, end_d)
        if resp.ok and resp.candles:
            rows = [{"date": c.date, "open": c.open, "high": c.high,
                     "low": c.low, "close": c.close, "volume": c.volume}
                    for c in resp.candles]
            n = db.upsert_candles(code, rows)
            filled += n
    if filled:
        print(f"  [filler] {code}: 补缺 {filled} 条")

    return db.get_candles(code, required_days)


def _get_trading_days(start: str, end: str) -> List[str]:
    """获取交易日历（走 date_sequence，不耗历史配额）"""
    from data_source.ifind_client import IFindClient
    client = IFindClient()
    try:
        data = client._http(
            "/date_sequence",
            {"codes": "000001.SH", "startdate": start, "enddate": end,
             "functionpara": {"Days": "Tradedays", "Fill": "Omit"},
             "indipara": []},
            timeout=10
        )
        if data and data.get("errorcode") == 0:
            tables = data.get("tables", [])
            if tables:
                return tables[0].get("time", [])
    except Exception:
        pass
    return []


def _batch_dates(dates: List[str]) -> List[tuple]:
    """将日期列表合并为连续区间 [(start, end), ...]"""
    if not dates:
        return []
    sorted_dates = sorted(dates)
    batches = []
    batch_start = sorted_dates[0]
    prev = sorted_dates[0]
    for d in sorted_dates[1:]:
        # 简单连续判断（不考虑周末，因为 missing 本身就是交易日）
        if d <= prev:
            continue
        # 如果间隔超过 10 天，另起一批
        from datetime import datetime, timedelta
        try:
            dp = datetime.strptime(prev, "%Y-%m-%d")
            dc = datetime.strptime(d, "%Y-%m-%d")
            if (dc - dp).days > 10:
                batches.append((batch_start, prev))
                batch_start = d
        except ValueError:
            pass
        prev = d
    batches.append((batch_start, prev))
    return batches
