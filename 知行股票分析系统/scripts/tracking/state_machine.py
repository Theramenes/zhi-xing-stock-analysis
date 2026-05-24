"""B1 状态机 + 变化检测"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.portfolio_db import (
    get_watchlist_item, update_watchlist_status,
    update_b1_stage, get_b1_tracking, detect_watchlist_changes,
)


# stage 枚举
WATCHING = "watching"
NEAR_B1 = "near_b1"
B1 = "b1"
OBSERVING = "observing"
BOUGHT = "bought"
HOLDING = "holding"
SELL_CANDIDATE = "sell_candidate"
SOLD = "sold"
ARCHIVED = "archived"


def transition(current_stage: str, indicators: dict) -> str:
    """
    根据当前 stage 和当日指标决定下一 stage。
    返回新的 stage 名称。
    """
    j = indicators.get("J", 999)
    signals = indicators.get("信号", [])
    trend = indicators.get("趋势", "")
    score = indicators.get("评分", 0)
    has_b1 = bool(signals)

    # --- 建档/持仓线 ---
    if current_stage in (BOUGHT, HOLDING):
        if not has_b1 and j > 50 and trend == "空头":
            return SELL_CANDIDATE
        if trend == "空头" and score <= 2:
            return SELL_CANDIDATE
        return HOLDING

    if current_stage == SELL_CANDIDATE:
        return SELL_CANDIDATE  # 需要用户确认才能变 SOLD

    if current_stage == SOLD:
        return SOLD

    # --- 信号线 ---
    if current_stage == WATCHING:
        if has_b1:
            return B1
        if j < 20:
            return NEAR_B1
        return WATCHING

    if current_stage == NEAR_B1:
        if has_b1:
            return B1
        return NEAR_B1

    if current_stage == B1:
        if has_b1:
            return B1
        # B1 消失 → 进入观察期
        return OBSERVING

    if current_stage == OBSERVING:
        if has_b1:
            return B1  # 观察期间恢复 B1
        if j < 20:
            return NEAR_B1  # 至少还接近
        return OBSERVING

    if current_stage == ARCHIVED:
        return ARCHIVED

    return WATCHING


def compute_next_stage(code: str, indicators: dict) -> str:
    """便利方法：查当前 stage 并计算下一个 stage"""
    item = get_watchlist_item(code)
    if not item:
        return WATCHING if indicators.get("信号") else WATCHING
    current = item.get("status", "active")
    tracking = get_b1_tracking(code, limit=1)
    current_stage = tracking[-1]["stage"] if tracking else WATCHING
    return transition(current_stage, indicators)


def apply_transition(code: str, indicators: dict) -> dict:
    """
    完整执行一次状态转换（读 → 算 → 写）。
    返回 {"code": ..., "from": ..., "to": ..., "memo": ...}
    """
    tracking = get_b1_tracking(code, limit=1)
    from_stage = tracking[-1]["stage"] if tracking else WATCHING
    to_stage = transition(from_stage, indicators)
    has_b1 = bool(indicators.get("信号", []))
    j = indicators.get("J", 999)

    # 写 b1_tracking
    memo = ""
    if from_stage != to_stage:
        memo = f"{from_stage} → {to_stage}"
    update_b1_stage(code, to_stage, indicators, memo)

    # 同步 watchlist status
    if to_stage in (B1, NEAR_B1) and has_b1:
        update_watchlist_status(code, "active", f"B1信号: {indicators.get('信号')}")
    elif to_stage == OBSERVING:
        update_watchlist_status(code, "observing", "B1消失, 进入观察期")

    return {"code": code, "from": from_stage, "to": to_stage, "memo": memo}


def generate_alerts(positions: list, watchlist_items: list) -> list:
    """根据持仓/关注票变化生成预警列表"""
    alerts = []
    for wl in watchlist_items:
        code = wl.get("code") if isinstance(wl, dict) else wl
        changes = detect_watchlist_changes(code)
        if changes.get("changed"):
            alerts.append({
                "code": code, "name": wl.get("name", ""),
                "type": "watchlist_change", "changes": changes.get("changes", [])
            })

    for pos in (positions or []):
        code = pos.get("code") if isinstance(pos, dict) else pos
        tracking = get_b1_tracking(code, limit=1)
        if tracking and tracking[-1]["stage"] == SELL_CANDIDATE:
            alerts.append({
                "code": code, "name": pos.get("name", ""),
                "type": "sell_candidate",
                "detail": "趋势转空或无B1信号，建议关注是否减仓"
            })

    return alerts
