"""
交易日历管理 — iFind HTTP 优先, baostock 降级, 纯日历日兜底
每次调用 get_trading_days() 自动检查更新到最新
"""
from datetime import datetime, timedelta
from typing import List


def fetch_trading_days(start: str, end: str) -> List[str]:
    """获取交易日列表。四级降级：新浪 → iFind → baostock → 日历日估算"""

    # 0. akshare 新浪交易日历（全量缓存，最快）
    days = _try_sina(start, end)
    if days:
        print(f"  [calendar] sina: {len(days)} 天")
        return days

    # 1. iFind HTTP
    days = _try_ifind(start, end)
    if days:
        print(f"  [calendar] iFind: {len(days)} 天")
        return days

    # 2. baostock
    days = _try_baostock(start, end)
    if days:
        print(f"  [calendar] baostock: {len(days)} 天")
        return days

    # 3. 纯日历日估算（跳过周六日）
    print("  [calendar] 日历估算")
    days = []
    s = datetime.strptime(start, "%Y-%m-%d") if isinstance(start, str) else start
    e = datetime.strptime(end, "%Y-%m-%d") if isinstance(end, str) else end
    delta = s
    while delta <= e:
        if delta.weekday() < 5:
            days.append(delta.strftime("%Y-%m-%d"))
        delta += timedelta(days=1)
    return days


def _try_sina(start: str, end: str) -> List[str] | None:
    """akshare 新浪交易日历 — 全量返回，只过滤日期范围"""
    try:
        import akshare as ak
        df = ak.tool_trade_date_hist_sina()
        if df is None or df.empty:
            return None
        all_dates = df["trade_date"].astype(str).tolist()
        return [d for d in all_dates if start <= d <= end]
    except Exception:
        return None


def _try_ifind(start: str, end: str) -> List[str] | None:
    try:
        from data_source.ifind_client import IFindClient
        client = IFindClient()
        if not client.is_available():
            return None
        data = client._http(
            "/date_sequence",
            {"codes": "000001.SH", "startdate": start, "enddate": end,
             "functionpara": {"Days": "Tradedays", "Fill": "Omit"},
             "indipara": [{"indicator": "ths_close_price_stock", "indiparams": ["", "", ""]}]},
            timeout=15,
        )
        if not data or data.get("errorcode") != 0:
            return None
        tables = data.get("tables", [])
        if not tables:
            return None
        return [d[:10] for d in tables[0].get("time", [])]
    except Exception:
        return None


def _try_baostock(start: str, end: str) -> List[str] | None:
    try:
        import baostock as bs
        lg = bs.login()
        if lg.error_code != '0':
            return None
        rs = bs.query_trade_dates(start_date=start, end_date=end)
        if rs.error_code != '0':
            bs.logout()
            return None
        days = []
        while rs.next():
            r = rs.get_row_data()
            if r[1] == '1':  # is_trading_day = 1
                days.append(r[0])
        bs.logout()
        return days if days else None
    except Exception:
        return None
