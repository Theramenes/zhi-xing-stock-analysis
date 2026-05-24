"""
akshare 财务数据 — 营收/利润/ROE/毛利率/现金流
抄 zhixinglu app/data/financial_data.py
"""
import akshare as ak
import pandas as pd


def _safe_float(val):
    """安全转为 float"""
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").replace(",", "").replace("亿", "").replace("万", ""))
    except (ValueError, TypeError):
        return None


def get_financial_summary(symbol: str) -> dict | None:
    """
    获取财务摘要 — 抄 zhixinglu get_financial_summary()
    返回最近5期的关键财务指标
    """
    try:
        df = ak.stock_financial_abstract_ths(symbol=symbol)
        if df is None or df.empty:
            return None
        # 取最近5期
        recent = df.tail(5).copy()
        records = []
        for _, row in recent.iterrows():
            records.append({
                "报告期": str(row.get("报告期", row.get("年度", ""))),
                "营业总收入": _safe_float(row.get("营业总收入")),
                "净利润": _safe_float(row.get("净利润")),
                "销售毛利率": _safe_float(row.get("销售毛利率")),
                "净资产收益率": _safe_float(row.get("净资产收益率")),
                "营业总收入同比增长": _safe_float(row.get("营业总收入同比增长")),
                "净利润同比增长": _safe_float(row.get("净利润同比增长")),
                "每股净资产": _safe_float(row.get("每股净资产")),
                "每股收益": _safe_float(row.get("每股收益")),
            })
        return {
            "records": records,
            "latest": records[-1] if records else None,
        }
    except Exception:
        return None


def get_cashflow(symbol: str) -> dict | None:
    """现金流量表"""
    try:
        df = ak.stock_financial_report_sina(symbol=symbol, symbol_="现金流量表")
        if df is None or df.empty:
            return None
        recent = df.tail(3).copy()
        records = []
        for _, row in recent.iterrows():
            records.append({
                "报告期": str(row.get("报告期", "")),
                "经营活动现金流净额": _safe_float(row.get("经营活动产生的现金流量净额")),
                "资本支出": _safe_float(row.get("购建固定资产、无形资产和其他长期资产支付的现金")),
            })
        latest = records[-1] if records else {}
        return {
            "records": records,
            "latest_op_cashflow": latest.get("经营活动现金流净额"),
            "latest_capex": latest.get("资本支出"),
        }
    except Exception:
        return None


def get_profit_sheet(symbol: str) -> dict | None:
    """利润表"""
    try:
        df = ak.stock_financial_report_sina(symbol=symbol, symbol_="利润表")
        if df is None or df.empty:
            return None
        recent = df.tail(3).copy()
        records = []
        for _, row in recent.iterrows():
            records.append({
                "报告期": str(row.get("报告期", "")),
                "营业收入": _safe_float(row.get("营业收入")),
                "营业成本": _safe_float(row.get("营业成本")),
                "净利润": _safe_float(row.get("净利润")),
            })
        return {"records": records}
    except Exception:
        return None


def get_dividend_history(symbol: str) -> dict | None:
    """分红历史"""
    try:
        df = ak.stock_fhps_detail_ths(symbol=symbol)
        if df is None or df.empty:
            return None
        recent = df.tail(5).copy()
        records = []
        for _, row in recent.iterrows():
            records.append({
                "报告期": str(row.get("报告期", "")),
                "股息率": _safe_float(row.get("股息率")),
                "每股派息": _safe_float(row.get("每股派息")),
            })
        return {
            "records": records,
            "latest_yield": records[-1].get("股息率") if records else None,
        }
    except Exception:
        return None


def get_financial_quality(financials: dict | None, cashflow: dict | None) -> dict:
    """
    生成财务质量判断（抄 JusticePlutus derive_quality_summary）
    """
    quality = {
        "profit_quality": "未知",
        "cashflow_health": "未知",
        "growth_visibility": "未知",
    }
    latest = financials.get("latest") if financials else None
    if latest:
        gross_margin = latest.get("销售毛利率") or 0
        net_margin = 0
        rev = latest.get("营业总收入") or 1
        profit = latest.get("净利润") or 0
        if rev > 0:
            net_margin = (profit / rev) * 100
        roe = latest.get("净资产收益率") or 0
        if gross_margin >= 40 and net_margin >= 15 and roe >= 15:
            quality["profit_quality"] = "强"
        elif net_margin >= 8 or roe >= 8:
            quality["profit_quality"] = "稳定"
        else:
            quality["profit_quality"] = "弱"

        growth = latest.get("净利润同比增长") or 0
        if growth >= 20:
            quality["growth_visibility"] = "高增长"
        elif growth >= 5:
            quality["growth_visibility"] = "中速增长"
        elif growth < -10:
            quality["growth_visibility"] = "下滑"
        else:
            quality["growth_visibility"] = "低速"

    if cashflow:
        op_cf = cashflow.get("latest_op_cashflow") or 0
        if latest and latest.get("净利润") and latest["净利润"] > 0:
            cf_ratio = op_cf / latest["净利润"]
            if cf_ratio >= 0.8:
                quality["cashflow_health"] = "健康"
            elif cf_ratio >= 0.3:
                quality["cashflow_health"] = "一般"
            else:
                quality["cashflow_health"] = "弱"
    return quality
