"""
每日数据更新器 — 智能分层获取

策略:
  today    → THS_RQ 实时行情（当日盘中/盘后 OHLCV）
  yesterday back → snapshot 逐日补（THS_SS，15:00:00 快照）
  剩余缺口   → date_sequence 批量兜底
"""
import sys, os, time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from .db import get_db
from data_source.ifind_client import IFindClient


def daily_update(code: str, required_days: int = 114):
    """
    智能分层更新单只股票的 K 线数据。
    ① 更新交易日历
    ② today → THS_RQ
    ③ yesterday → snapshot 逐日
    ④ 缺口 → date_sequence 批量兜底
    """
    db = get_db()
    client = IFindClient()
    # snapshot 需要 .SZ/.SH 后缀
    ifnd_code = IFindClient._to_ifind_code(code)
    today_str = datetime.now().strftime("%Y-%m-%d")

    # ① 交易日历
    db.ensure_trading_calendar()

    # ② today: THS_RQ 实时行情
    print(f"  [{code}] today: THS_RQ...", end=" ")
    resp = client.get_realtime_ohlcv(ifnd_code)
    if resp and resp.candles:
        rows = [{"date": c.date, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in resp.candles]
        n = db.upsert_candles(code, rows, source="ifind")
        print(f"{n}条", end="")
    else:
        print("跳过", end="")
    print()

    # ③ yesterday back: snapshot 逐日（走交易日历倒推）
    trading_days = db.get_trading_days("2025-01-01", today_str)
    existing = db.get_candles(code, required_days + 30)
    existing_dates = {c["date"] for c in existing}

    # 需要补的交易日（最近 required_days 个）
    need_days = trading_days[-required_days:]
    missing = [d for d in need_days if d not in existing_dates and d != today_str]

    if missing:
        print(f"  [{code}] snapshot 补 {len(missing)} 天...", end=" ")
        filled = 0
        for d in missing:
            resp = client._try_snapshot(ifnd_code, d)
            if resp and resp.candles:
                rows = [{"date": c.date, "open": c.open, "high": c.high,
                         "low": c.low, "close": c.close, "volume": c.volume}
                        for c in resp.candles]
                db.upsert_candles(code, rows, source="ifind")
                filled += len(rows)
            time.sleep(0.1)
        print(f"{filled}条")

    # ④ 缺口兜底
    still = db.get_missing_dates(code, need_days)
    if still:
        print(f"  [{code}] date_sequence 兜底 {len(still)} 天...")
        batches = _batch_dates(still)
        for start_d, end_d in batches:
            resp = client.get_kline_range(code, start_d, end_d)
            if resp.ok and resp.candles:
                rows = [{"date": c.date, "open": c.open, "high": c.high,
                         "low": c.low, "close": c.close, "volume": c.volume}
                        for c in resp.candles]
                db.upsert_candles(code, rows, source="ifind")
            time.sleep(0.3)

    candles = db.get_candles(code, required_days)
    print(f"  [{code}] 完成: {len(candles)} 天  {candles[0]['date'] if candles else '?'} ~ {candles[-1]['date'] if candles else '?'}")
    return candles


def _batch_dates(dates):
    """合并连续日期"""
    if not dates: return []
    sorted_dates = sorted(dates)
    batches, start = [], sorted_dates[0]
    prev = start
    for d in sorted_dates[1:]:
        try:
            if (datetime.strptime(d, "%Y-%m-%d") - datetime.strptime(prev, "%Y-%m-%d")).days > 10:
                batches.append((start, prev)); start = d
        except: pass
        prev = d
    batches.append((start, prev))
    return batches
