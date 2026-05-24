"""
估值模型 — 格雷厄姆数 + 反向DCF
抄 zhixinglu app/ai/valuation_models.py（最可靠的两个）
"""
from types import SimpleNamespace

try:
    from valueinvest.valuation.graham import GrahamNumber
    from valueinvest.valuation.dcf import ReverseDCF
    _HAS_VALUEINVEST = True
except ImportError:
    _HAS_VALUEINVEST = False

DEFAULT_WACC = 0.10
DEFAULT_TERMINAL_GROWTH = 0.025


def graham_number(eps: float, bvps: float, price: float) -> dict | None:
    """
    格雷厄姆数 = sqrt(22.5 × EPS × BVPS)
    最稳定 — 数据需求最少（EPS + BVPS）
    """
    if not _HAS_VALUEINVEST:
        return {"method": "格雷厄姆数", "error": "valueinvest 未安装"}
    try:
        if not eps or eps <= 0 or not bvps or bvps <= 0 or not price:
            return None
        stock = SimpleNamespace(eps=eps, bvps=bvps, current_price=price)
        result = GrahamNumber().calculate(stock)
        if result.fair_value and result.fair_value > 0:
            return {
                "method": "格雷厄姆数",
                "fair_value": round(result.fair_value, 2),
                "premium_discount": round(result.premium_discount, 2) if result.premium_discount else 0,
                "assessment": result.assessment or "定价合理",
            }
    except Exception:
        pass
    return None


def reverse_dcf(fcf: float, shares: float, price: float,
                wacc: float = DEFAULT_WACC, terminal_growth: float = DEFAULT_TERMINAL_GROWTH) -> dict | None:
    """
    反向DCF — 从当前价格反推市场隐含的预期增速
    最客观 — 不假设增长，让用户判断增速是否合理
    """
    if not _HAS_VALUEINVEST:
        return {"method": "反向DCF", "error": "valueinvest 未安装"}
    try:
        if not fcf or fcf <= 0 or not shares or shares <= 0 or not price:
            return None
        stock = SimpleNamespace(
            fcf=fcf,
            shares_outstanding=shares,
            current_price=price,
            net_debt=0,
            discount_rate=wacc * 100 if wacc < 1 else wacc,
            terminal_growth=terminal_growth * 100 if terminal_growth < 1 else terminal_growth,
        )
        result = ReverseDCF().calculate(stock)
        implied_growth = result.details.get("implied_growth_1_5", None) if hasattr(result, "details") else None
        return {
            "method": "反向DCF",
            "fair_value": round(price, 2),
            "premium_discount": 0.0,
            "assessment": "反向DCF — 市场定价基准",
            "implied_growth_5y": round(implied_growth, 1) if implied_growth else None,
        }
    except Exception:
        pass
    return None


def run_valuation_summary(financials: dict, cashflow: dict, symbol: str = "") -> list[dict]:
    """
    运行两类估值。需要 G1 拉取的财务数据。
    financials: {"records": [{...5期}]}
    cashflow: {"latest_op_cashflow": N, "latest_capex": N}
    返回: [{"method":..., "fair_value":..., "premium_discount":..., "assessment":...}, ...]
    """
    latest = financials.get("latest") if financials else {}
    eps = latest.get("每股收益")
    bvps = latest.get("每股净资产")
    price = None  # price 需要外部传入，G3 从 B1 指标获取 last price

    results = []

    if eps and bvps:
        # price 暂时从 B1 indicators 取，这里预留
        gn = graham_number(eps, bvps, price or 1)
        if gn:
            results.append(gn)

    if cashflow:
        op_cf = cashflow.get("latest_op_cashflow") or 0
        capex = cashflow.get("latest_capex") or 0
        fcf = op_cf - capex
        if fcf > 0:
            # shares 需要外部传入
            rd = reverse_dcf(fcf, 1, price or 1)
            if rd:
                results.append(rd)

    return results
