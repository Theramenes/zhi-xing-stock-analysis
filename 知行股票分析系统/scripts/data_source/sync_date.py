"""
统一交易日判断 — 所有数据操作的前置逻辑

规则:
  1. 获取当前时间
  2. 确保交易日历最新
  3. 判断今天是否交易日
  4. 交易日 && >15:00 → 增量更新今日
  5. 交易日 && <15:00 → skip 今天，但检查最近交易日覆盖
  6. 非交易日 → 检查最近交易日覆盖
  7. 最近交易日数据不足 → backfill

用法:
    from data_source.sync_date import resolve_sync_target
    target_date, action = resolve_sync_target()
    # target_date: "2026-06-08" 或 None
    # action: "today" / "backfill" / "skip"
"""
from datetime import datetime, time
from typing import Optional, Tuple


def resolve_sync_target() -> Tuple[Optional[str], str]:
    """决定今天应该拉取哪个交易日的数据。"""
    from storage.db import get_db
    db = get_db()
    db.ensure_trading_calendar()

    now = datetime.now()
    today_str = now.strftime("%Y-%m-%d")

    all_days = db.get_trading_days("2020-01-01", today_str)
    is_trading_day = today_str in all_days
    after_close = now.time() >= time(15, 0)

    # 1. 交易日已收盘 → 拉今天
    if is_trading_day and after_close:
        return today_str, "today"

    # 2. 构建候选回填日期列表（排除今天盘中）
    backfill_candidates = []
    if len(all_days) >= 1 and all_days[-1] != today_str:
        backfill_candidates.append(all_days[-1])     # 最近交易日（非今天）
    elif len(all_days) >= 2:
        backfill_candidates.append(all_days[-2])     # 昨天是今天时取前天
    if len(all_days) >= 2 and is_trading_day:
        # 交易日盘中：今天不能拉，但检查昨天
        y = all_days[-1] if all_days[-1] != today_str else (all_days[-2] if len(all_days) >= 2 else None)
        if y and y not in backfill_candidates:
            backfill_candidates.append(y)

    # 3. 逐个检查覆盖度
    for d in backfill_candidates:
        cnt = db.conn.execute(
            "SELECT COUNT(DISTINCT code) FROM stock_daily WHERE date=?", (d,)
        ).fetchone()[0]
        if cnt < 100:
            return d, "backfill"

    return None, "skip"


def get_last_sync_date() -> Optional[str]:
    """获取数据库最近一次同步的交易日"""
    from storage.db import get_db
    db = get_db()
    row = db.conn.execute(
        "SELECT MAX(date) FROM stock_daily WHERE date IS NOT NULL"
    ).fetchone()
    return row[0] if row else None
