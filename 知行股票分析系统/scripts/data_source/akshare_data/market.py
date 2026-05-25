"""
akshare 市场数据 — 指数/板块排名/北向资金/个股资金流
抄 zhixinglu app/data/letter_data.py get_market_overview() + get_stock_detail()
"""
import akshare as ak
from .rate_limiter import with_rate_limit


def _safe_float(val):
    if val is None:
        return None
    try:
        return float(str(val).replace("%", "").replace(",", ""))
    except (ValueError, TypeError):
        return None


@with_rate_limit
def get_market_overview() -> dict:
    """市场大局 — 4大指数 + 北向资金 + 领涨/领跌板块"""
    result = {}

    # 指数
    try:
        spot = ak.stock_zh_index_spot_em()
        for idx_name in ["上证指数", "深证成指", "创业板指", "沪深300"]:
            row = spot[spot["名称"] == idx_name]
            if not row.empty:
                r = row.iloc[0]
                result[idx_name] = {
                    "最新价": _safe_float(r.get("最新价")),
                    "涨跌幅": _safe_float(r.get("涨跌幅")),
                    "成交额": _safe_float(r.get("成交额")),
                }
    except Exception:
        pass

    # 北向资金
    try:
        hsgt = ak.stock_hsgt_north_net_flow_in_em(symbol="北上")
        if hsgt is not None and not hsgt.empty:
            latest = hsgt.iloc[-1]
            flow_val = _safe_float(latest.get("value", latest.get("当日净流入", 0)))
            result["北向资金"] = {"净流入": flow_val}
    except Exception:
        pass

    # 领涨/领跌板块
    try:
        board = ak.stock_board_industry_name_em()
        if board is not None and not board.empty:
            board_sorted = board.sort_values("涨跌幅", ascending=False)
            top5 = board_sorted.head(5)[["板块名称", "涨跌幅"]].copy()
            top5["涨跌幅"] = top5["涨跌幅"].apply(_safe_float)
            bottom5 = board_sorted.tail(5)[["板块名称", "涨跌幅"]].copy()
            bottom5["涨跌幅"] = bottom5["涨跌幅"].apply(_safe_float)
            result["领涨板块"] = top5.to_dict("records")
            result["领跌板块"] = bottom5.to_dict("records")
    except Exception:
        pass

    return result


def get_fund_flow(symbol: str) -> dict | None:
    """个股资金流向 — 主力/超大单净流入"""
    try:
        df = ak.stock_individual_fund_flow(stock=symbol, market="sh" if symbol.startswith("6") else "sz")
        if df is None or df.empty:
            return None
        latest = df.iloc[-1]
        return {
            "主力净流入": _safe_float(latest.get("主力净流入-净额", 0)),
            "超大单净流入": _safe_float(latest.get("超大单净流入-净额", 0)),
            "大单净流入": _safe_float(latest.get("大单净流入-净额", 0)),
        }
    except Exception:
        return None
