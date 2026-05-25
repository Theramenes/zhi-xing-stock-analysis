"""
基本面数据级联 — iFind → efinance → akshare
每类数据一个函数，自动 fallback，共享熔断状态
"""
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_source.registry import registry as ds_registry

# 全局熔断状态
_ifind_fail_count = 0
_ifind_disabled = False
_FUSE_COOLDOWN = 300


def _ifind_ok():
    global _ifind_fail_count, _ifind_disabled
    _ifind_fail_count = 0


def _ifind_fail():
    global _ifind_fail_count, _ifind_disabled
    _ifind_fail_count += 1
    if _ifind_fail_count >= 3:
        _ifind_disabled = True


def _try_ifind(searchstring: str) -> dict | None:
    """带熔断的 iFind 调用"""
    global _ifind_disabled
    if _ifind_disabled:
        return None
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        _ifind_disabled = True
        return None
    try:
        payload = json.dumps({"searchstring": searchstring, "searchtype": "stock"}, ensure_ascii=False)
        data = ifind._call("endpoint-call", "--name", "a_share_common_query",
                           "--payload", payload, timeout=10)
        if not data or not data.get("ok"):
            _ifind_fail()
            return None
        _ifind_ok()
        return data
    except Exception:
        _ifind_fail()
        return None


def _safe_num(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return val
    try:
        return float(str(val).replace(",", "").replace("%", "").replace("亿", "").replace("万", ""))
    except (ValueError, TypeError):
        return None


def get_fundamentals(code: str, name: str = "") -> dict:
    """基本面：iFind → akshare"""
    # iFind
    if not _ifind_disabled:
        data = _try_ifind(f"{name} 营业总收入 归母净利润 ROE 销售毛利率 经营现金流")
        if data:
            tables = data.get("data", {}).get("tables", [])
            if tables:
                tb = tables[0].get("table", {})
                keys = list(tb.keys())
                if keys:
                    idx = len(tb[keys[0]]) - 1
                    result = {"source": "ifind"}
                    col_map = {"营业总收入": "revenue", "归母净利润": "net_profit",
                               "ROE": "roe", "销售毛利率": "gross_margin",
                               "经营现金流": "op_cashflow"}
                    for cn, key in col_map.items():
                        for k in keys:
                            if cn in str(k):
                                val = tb[k][idx] if idx < len(tb[k]) else None
                                if val:
                                    result[key] = _safe_num(val)
                    if len(result) > 1:
                        return result

    # akshare fallback
    try:
        from data_source.akshare_data.financial import get_financial_summary, get_cashflow, get_financial_quality
        fs = get_financial_summary(code)
        if fs and fs.get("latest"):
            latest = fs["latest"]
            cf = get_cashflow(code)
            quality = get_financial_quality(fs, cf)
            return {
                "revenue": latest.get("营业总收入"),
                "net_profit": latest.get("净利润"),
                "roe": latest.get("净资产收益率"),
                "gross_margin": latest.get("销售毛利率"),
                "net_margin": (latest.get("净利润") / latest.get("营业总收入") * 100) if latest.get("营业总收入") and latest.get("净利润") else None,
                "op_cashflow": cf.get("latest_op_cashflow") if cf else None,
                "eps": latest.get("每股收益"),
                "bvps": latest.get("每股净资产"),
                "growth_revenue": latest.get("营业总收入同比增长"),
                "growth_profit": latest.get("净利润同比增长"),
                "quality": quality,
                "source": "akshare",
            }
    except Exception:
        pass
    return {"source": "none"}


def get_valuation(code: str, name: str = "") -> dict:
    """估值：iFind → akshare"""
    result = {}

    if not _ifind_disabled:
        data = _try_ifind(f"{name} 市盈率 市净率 总市值 流通市值")
        if data:
            tables = data.get("data", {}).get("tables", [])
            if tables:
                tb = tables[0].get("table", {})
                keys = list(tb.keys())
                if keys:
                    idx = len(tb[keys[0]]) - 1
                    for cn, key in [("市盈率", "pe"), ("市净率", "pb"), ("总市值", "total_mv"), ("流通市值", "circ_mv")]:
                        for k in keys:
                            if cn in str(k):
                                val = tb[k][idx] if idx < len(tb[k]) else None
                                if val:
                                    result[key] = _safe_num(val)
                    if result:
                        result["source"] = "ifind"

    # akshare fallback
    try:
        from data_source.akshare_data.valuation import get_valuation_history
        hist = get_valuation_history(code)
        if hist:
            pe = hist.get("pe", {})
            pb = hist.get("pb", {})
            if pe:
                result["pe"] = result.get("pe") or pe.get("current")
                result["pe_pct_5y"] = pe.get("pct_5y")
            if pb:
                result["pb"] = result.get("pb") or pb.get("current")
                result["pb_pct_5y"] = pb.get("pct_5y")
            if not result.get("source"):
                result["source"] = "akshare"
    except Exception:
        pass
    return result if result else {"source": "none"}


def get_news_and_reports(code: str) -> dict:
    """消息面：akshare"""
    try:
        from data_source.akshare_data.news_info import get_stock_news, get_research_reports, get_announcements
        news = get_stock_news(code, 10)
        reports = get_research_reports(code, 5)
        announcements = get_announcements(code, 10)
        return {"news": news or [], "reports": reports or [], "announcements": announcements or [], "source": "akshare"}
    except Exception:
        return {"news": [], "reports": [], "announcements": [], "source": "none"}


def get_market_context() -> dict:
    """市场大局：优先 sector_cascade"""
    try:
        from data_source.sector_cascade import SectorCascade
        sc = SectorCascade()
        rankings = sc.get_sector_rankings()
        top = rankings.get("top", [])
        bottom = rankings.get("bottom", [])
        src = rankings.get("source", "?")
        result = {"source": src, "领涨板块": top, "领跌板块": bottom}
        # 补指数
        try:
            from data_source.akshare_data.market import get_market_overview
            mk = get_market_overview()
            for idx in ["上证指数", "深证成指", "创业板指", "沪深300"]:
                if idx in mk:
                    result[idx] = mk[idx]
            north = mk.get("北向资金")
            if north:
                result["北向资金"] = north
        except Exception:
            pass
        return result
    except Exception:
        try:
            from data_source.akshare_data.market import get_market_overview
            return get_market_overview()
        except Exception:
            return {}


def get_chip(code: str) -> dict | None:
    """筹码：akshare"""
    try:
        from data_source.akshare_data.chip import get_chip_distribution
        return get_chip_distribution(code)
    except Exception:
        return None


def get_fund_flow(code: str) -> dict | None:
    """资金流向：akshare"""
    try:
        from data_source.akshare_data.market import get_fund_flow
        return get_fund_flow(code)
    except Exception:
        return None
