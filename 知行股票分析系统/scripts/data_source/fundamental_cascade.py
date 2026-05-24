"""
基本面数据级联 — iFind → akshare → freeStockLine
每类数据一个函数，自动 fallback，返回统一的标准化 dict
"""
import json
import time
from data_source.registry import registry as ds_registry


def _try_ifind_fundamental(code: str, name: str) -> dict | None:
    """iFind 基本面查询 — 通过 a_share_common_query"""
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        return None
    try:
        searchstring = f"{name} 营业总收入 归属于母公司所有者的净利润 净资产收益率ROE 销售毛利率 销售净利率 资产负债率 经营活动产生的现金流量净额"
        payload = json.dumps({"searchstring": searchstring, "searchtype": "stock"}, ensure_ascii=False)
        data = ifind._call("endpoint-call", "--name", "a_share_common_query",
                           "--payload", payload, timeout=30)
        if not data or not data.get("ok"):
            return None
        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return None
        tb = tables[0].get("table", {})
        keys = list(tb.keys())
        if not keys:
            return None
        # 取最新一行
        idx = len(tb[keys[0]]) - 1
        result = {}
        col_map = {
            "营业总收入": "revenue", "归属于母公司所有者的净利润": "net_profit",
            "净资产收益率ROE": "roe", "销售毛利率": "gross_margin",
            "销售净利率": "net_margin", "资产负债率": "debt_ratio",
            "经营活动产生的现金流量净额": "op_cashflow",
        }
        for col_name, key in col_map.items():
            for k in keys:
                if col_name in str(k):
                    val = tb[k][idx] if idx < len(tb[k]) else None
                    if val:
                        result[key] = _safe_num(val)
        return result if result else None
    except Exception:
        return None


def _try_ifind_valuation(code: str, name: str) -> dict | None:
    """iFind 估值查询"""
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        return None
    try:
        searchstring = f"{name} 市盈率 市净率 总市值 流通市值"
        payload = json.dumps({"searchstring": searchstring, "searchtype": "stock"}, ensure_ascii=False)
        data = ifind._call("endpoint-call", "--name", "a_share_common_query",
                           "--payload", payload, timeout=30)
        if not data or not data.get("ok"):
            return None
        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return None
        tb = tables[0].get("table", {})
        keys = list(tb.keys())
        idx = len(tb[keys[0]]) - 1
        result = {}
        col_map = {
            "市盈率": "pe", "市净率": "pb",
            "总市值": "total_mv", "流通市值": "circ_mv",
        }
        for col_name, key in col_map.items():
            for k in keys:
                if col_name in str(k):
                    val = tb[k][idx] if idx < len(tb[k]) else None
                    if val:
                        result[key] = _safe_num(val)
        return result if result else None
    except Exception:
        return None


def _safe_num(val):
    """字符串转数字"""
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    try:
        s = str(val).replace(",", "").replace("%", "").replace("亿", "").replace("万", "")
        return float(s)
    except (ValueError, TypeError):
        return None


# ============================================================
# 级联函数 — 每类数据一个
# ============================================================

def get_fundamentals(code: str, name: str = "") -> dict:
    """
    基本面：iFind → akshare
    返回 {"revenue","net_profit","roe","gross_margin","net_margin","debt_ratio","op_cashflow","quality",...}
    """
    # 1. iFind
    result = _try_ifind_fundamental(code, name)
    if result:
        result["source"] = "ifind"
        return result

    # 2. akshare
    try:
        from data_source.akshare_data.financial import get_financial_summary, get_cashflow, get_financial_quality
        time.sleep(1.5)
        fs = get_financial_summary(code)
        if fs and fs.get("latest"):
            latest = fs["latest"]
            cf = get_cashflow(code)
            quality = get_financial_quality(fs, cf)
            result = {
                "revenue": latest.get("营业总收入"),
                "net_profit": latest.get("净利润"),
                "roe": latest.get("净资产收益率"),
                "gross_margin": latest.get("销售毛利率"),
                "net_margin": (latest.get("净利润") / latest.get("营业总收入") * 100) if latest.get("营业总收入") and latest.get("净利润") else None,
                "debt_ratio": None,
                "op_cashflow": cf.get("latest_op_cashflow") if cf else None,
                "eps": latest.get("每股收益"),
                "bvps": latest.get("每股净资产"),
                "growth_revenue": latest.get("营业总收入同比增长"),
                "growth_profit": latest.get("净利润同比增长"),
                "quality": quality,
                "source": "akshare",
            }
            return result
    except Exception:
        pass

    return {"source": "none"}


def get_valuation(code: str, name: str = "") -> dict:
    """
    估值：iFind → akshare
    返回 {"pe","pb","total_mv","circ_mv","pe_pct","pb_pct",...}
    """
    result = {}

    # 1. iFind
    ifind_val = _try_ifind_valuation(code, name)
    if ifind_val:
        result.update(ifind_val)
        result["source"] = "ifind"

    # 2. akshare (补 PE/PB 分位)
    try:
        from data_source.akshare_data.valuation import get_valuation_history
        time.sleep(1.5)
        hist = get_valuation_history(code)
        if hist:
            pe = hist.get("pe", {})
            pb = hist.get("pb", {})
            if pe:
                result["pe"] = result.get("pe") or pe.get("current")
                result["pe_pct_5y"] = pe.get("pct_5y")
                result["pe_min_5y"] = pe.get("min_5y")
                result["pe_max_5y"] = pe.get("max_5y")
            if pb:
                result["pb"] = result.get("pb") or pb.get("current")
                result["pb_pct_5y"] = pb.get("pct_5y")
            if not result.get("source"):
                result["source"] = "akshare"
    except Exception:
        pass

    return result if result else {"source": "none"}


def get_news_and_reports(code: str) -> dict:
    """
    消息面：akshare（iFind 不提供新闻，freeStockLine 可选）
    """
    try:
        from data_source.akshare_data.news_info import get_stock_news, get_research_reports, get_announcements
        time.sleep(1.5)
        news = get_stock_news(code, 10)
        reports = get_research_reports(code, 5)
        announcements = get_announcements(code, 10)
        return {
            "news": news or [],
            "reports": reports or [],
            "announcements": announcements or [],
            "source": "akshare",
        }
    except Exception:
        return {"news": [], "reports": [], "announcements": [], "source": "none"}


def get_market_context() -> dict:
    """市场大局：akshare"""
    try:
        from data_source.akshare_data.market import get_market_overview
        time.sleep(1.5)
        return get_market_overview()
    except Exception:
        return {}


def get_chip(code: str) -> dict | None:
    """筹码：akshare"""
    try:
        from data_source.akshare_data.chip import get_chip_distribution
        time.sleep(1.5)
        return get_chip_distribution(code)
    except Exception:
        return None


def get_fund_flow(code: str) -> dict | None:
    """资金流向：akshare"""
    try:
        from data_source.akshare_data.market import get_fund_flow
        time.sleep(1.5)
        return get_fund_flow(code)
    except Exception:
        return None
