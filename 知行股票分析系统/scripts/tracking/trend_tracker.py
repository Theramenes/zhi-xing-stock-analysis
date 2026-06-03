"""
趋势追踪 — 日更时判定状态转移，关注列表分层管理

规则:
  弱势→拐头向上: 底部拐头 → 普通关注 level=2
  金叉: 白线上穿黄线 → 重点关注 level=1
  拐头向上→多头: 趋势确认 → 重点关注 level=1
  顶部预警: 多头→谨慎 → 保持关注, 加备注
  多头→谨慎(连续3天): 可能减仓 → 降级普通
"""
from datetime import datetime
from typing import Optional, List, Dict

from storage.db import get_db
from storage.portfolio_db import add_to_watchlist, set_watchlist_level


def compute_trend_state(code: str, candles: List[dict]) -> Optional[Dict]:
    """计算单只股票的趋势状态"""
    from indicators.trend_analyzer import TrendAnalyzer
    ta = TrendAnalyzer(code, candles)
    return ta.compute()


def detect_state_transition(code: str, prev_state: str, curr_state: str,
                            curr_trend: dict) -> list:
    """检测趋势状态转移，返回 [(action, reason, level)]"""
    actions = []

    # 弱势→拐头向上: 底部拐头
    if prev_state == "弱势" and curr_state == "拐头向上":
        actions.append(("add_or_upgrade", "底部拐头(弱势→拐头向上)", 2))

    # 金叉
    if curr_trend.get("cross") == "golden":
        actions.append(("upgrade", "金叉确认", 1))

    # 拐头向上→多头: 趋势确认
    if prev_state == "拐头向上" and curr_state == "多头":
        actions.append(("upgrade", "趋势确认(拐头向上→多头)", 1))

    # 多头→谨慎: 顶部预警
    if prev_state == "多头" and curr_state == "谨慎":
        actions.append(("warn", "顶部预警", None))

    # 首次出现拐头向上
    if curr_state == "拐头向上" and prev_state != "拐头向上" and prev_state != "多头":
        actions.append(("add_or_upgrade", "首次拐头向上", 2))

    return actions


def daily_trend_update(codes: List[str]) -> dict:
    """日更趋势追踪：给定代码列表，计算趋势+判定状态转移+更新关注列表

    Returns: {added_level1: [], added_level2: [], transitions: [], ...}
    """
    from storage.kline_filler import ensure_candles
    from indicators.trend_analyzer import TrendAnalyzer

    db = get_db()
    db.ensure_trading_calendar()
    today = db.conn.execute("SELECT MAX(date) FROM trading_calendar").fetchone()[0]

    added_1 = []
    added_2 = []
    transitions = []
    errors = []

    for code in codes:
        # 确保K线数据
        candles = ensure_candles(code, required_days=125)
        if not candles or len(candles) < 110:
            continue

        # 当前趋势
        curr = compute_trend_state(code, candles)
        if "error" in curr:
            errors.append((code, curr["error"]))
            continue

        curr_state = curr["state"]

        # 前一日趋势
        prev_state = "未知"
        prev_rows = db.conn.execute(
            "SELECT state FROM watchlist_daily WHERE code=? AND date<? ORDER BY date DESC LIMIT 1",
            (code, today)
        ).fetchone()
        if prev_rows:
            prev_state = prev_rows[0]

        # 记录当日趋势到 watchlist_daily
        try:
            db.conn.execute(
                "UPDATE watchlist_daily SET state=?, trend_score=? WHERE code=? AND date=?",
                (curr_state, curr["score"], code, today)
            )
        except Exception:
            pass

        # 判定状态转移
        actions = detect_state_transition(code, prev_state, curr_state, curr)
        for action, reason, level in actions:
            transitions.append({
                "code": code,
                "prev": prev_state,
                "curr": curr_state,
                "action": action,
                "reason": reason,
                "score": curr["score"],
            })
            if level == 1 and action in ("add_or_upgrade", "upgrade"):
                add_to_watchlist(code, "", source="trend", reason=reason,
                                 tags=["趋势", curr_state], level=1)
                added_1.append(code)
            elif level == 2 and action == "add_or_upgrade":
                add_to_watchlist(code, "", source="trend", reason=reason,
                                 tags=["趋势", curr_state], level=2)
                added_2.append(code)

    return {
        "date": today,
        "total": len(codes),
        "added_level1": added_1,
        "added_level2": added_2,
        "transitions": transitions,
        "errors": errors,
    }
