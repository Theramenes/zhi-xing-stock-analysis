"""
akshare 估值数据 — PE/PB历史分位 + 分析师预期 + 评级分布
抄 zhixinglu app/data/valuation_data.py + financial_data.py 分析师预测部分
"""
import akshare as ak


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


def get_valuation_history(symbol: str) -> dict | None:
    """PE/PB 5年历史 + 当前分位"""
    try:
        pe_df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市盈率", period="近五年")
        pb_df = ak.stock_zh_valuation_baidu(symbol=symbol, indicator="市净率", period="近五年")
        result = {}
        if pe_df is not None and not pe_df.empty:
            pe_values = pe_df["value"].dropna().tolist()
            pe_current = float(pe_values[-1]) if pe_values else None
            if pe_values and pe_current and pe_current > 0:
                pe_pct = sum(1 for v in pe_values if v < pe_current) / len(pe_values) * 100
            else:
                pe_pct = None
            result["pe"] = {
                "current": pe_current,
                "pct_5y": round(pe_pct, 1) if pe_pct is not None else None,
                "min_5y": float(min(pe_values)) if pe_values else None,
                "max_5y": float(max(pe_values)) if pe_values else None,
            }
        if pb_df is not None and not pb_df.empty:
            pb_values = pb_df["value"].dropna().tolist()
            pb_current = float(pb_values[-1]) if pb_values else None
            if pb_values and pb_current and pb_current > 0:
                pb_pct = sum(1 for v in pb_values if v < pb_current) / len(pb_values) * 100
            else:
                pb_pct = None
            result["pb"] = {
                "current": pb_current,
                "pct_5y": round(pb_pct, 1) if pb_pct is not None else None,
                "min_5y": float(min(pb_values)) if pb_values else None,
                "max_5y": float(max(pb_values)) if pb_values else None,
            }
        return result if result else None
    except Exception:
        return None


def get_profit_forecast(symbol: str) -> dict | None:
    """分析师盈利预测"""
    try:
        eps_df = ak.stock_profit_forecast_ths(symbol=symbol, indicator="预测年报每股收益")
        if eps_df is None or eps_df.empty:
            return None
        records = []
        for _, row in eps_df.iterrows():
            records.append({
                "年度": str(row.get("年度", "")),
                "机构数": int(row.get("机构数", 0)),
                "最小值": _safe_float(row.get("最小值")),
                "均值": _safe_float(row.get("均值")),
                "最大值": _safe_float(row.get("最大值")),
            })
        return {"eps_forecast": records}
    except Exception:
        return None


def get_ratings(symbol: str) -> dict | None:
    """机构评级分布"""
    try:
        df = ak.stock_profit_forecast_em(symbol=symbol)
        if df is None or df.empty:
            return None
        # 统计近6个月评级
        buy = sell = hold = neutral = reduce_hold = 0
        for _, row in df.tail(50).iterrows():
            rating = str(row.get("评级", "") or row.get("东财评级", ""))
            if "买入" in rating:
                buy += 1
            elif "增持" in rating:
                hold += 1
            elif "中性" in rating:
                neutral += 1
            elif "减持" in rating:
                reduce_hold += 1
            elif "卖出" in rating:
                sell += 1
        total = buy + hold + neutral + reduce_hold + sell
        return {
            "total": total,
            "buy": buy, "hold": hold, "neutral": neutral,
            "reduce": reduce_hold, "sell": sell,
        } if total > 0 else None
    except Exception:
        return None
