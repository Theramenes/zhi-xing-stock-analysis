"""
筹码分布 — akshare stock_cyq_em()
抄 JusticePlutus 筹码分析逻辑
"""
import akshare as ak


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_chip_distribution(symbol: str) -> dict | None:
    """获取筹码分布 — 获利比例 / 平均成本 / 集中度"""
    try:
        df = ak.stock_cyq_em(symbol=symbol)
        if df is None or df.empty:
            return None
        latest = df.iloc[-1]
        profit_ratio = _safe_float(latest.get("获利比例"))
        avg_cost = _safe_float(latest.get("平均成本"))
        concentration_90 = _safe_float(latest.get("90%筹码集中度"))
        concentration_70 = _safe_float(latest.get("70%筹码集中度"))
        return {
            "profit_ratio": profit_ratio / 100 if profit_ratio and profit_ratio > 1 else profit_ratio,
            "avg_cost": avg_cost,
            "concentration_90": concentration_90 / 100 if concentration_90 and concentration_90 > 1 else concentration_90,
            "concentration_70": concentration_70 / 100 if concentration_70 and concentration_70 > 1 else concentration_70,
            "chip_status": _derive_chip_status(profit_ratio, concentration_90),
        }
    except Exception:
        return None


def _derive_chip_status(profit_ratio: float | None, concentration_90: float | None) -> str:
    """推导筹码状态（抄 JusticePlutus _derive_chip_health）"""
    pr = profit_ratio or 0
    c90 = concentration_90 or 1
    if pr >= 0.9:
        return "获利盘极高，警惕"
    if c90 >= 0.25:
        return "筹码分散，警惕"
    if c90 < 0.15 and 0.3 <= pr < 0.7:
        return "筹码集中健康"
    return "一般"
