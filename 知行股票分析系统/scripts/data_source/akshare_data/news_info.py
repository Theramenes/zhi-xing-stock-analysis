"""
akshare 消息数据 — 新闻/研报/公告
抄 zhixinglu app/data/news_data.py
"""
import akshare as ak


def get_stock_news(symbol: str, limit: int = 30) -> list[dict] | None:
    """近期新闻"""
    try:
        df = ak.stock_news_em(symbol=symbol)
        if df is None or df.empty:
            return None
        recent = df.head(limit)
        return [
            {"title": str(row.get("新闻标题", "")), "time": str(row.get("发布时间", ""))}
            for _, row in recent.iterrows()
        ]
    except Exception:
        return None


def get_research_reports(symbol: str, limit: int = 10) -> list[dict] | None:
    """券商研报"""
    try:
        df = ak.stock_research_report_em(symbol=symbol)
        if df is None or df.empty:
            return None
        recent = df.head(limit)
        return [
            {
                "title": str(row.get("报告名称", "")),
                "org": str(row.get("机构", "")),
                "date": str(row.get("日期", "")),
                "rating": str(row.get("东财评级", "")),
            }
            for _, row in recent.iterrows()
        ]
    except Exception:
        return None


def get_announcements(symbol: str, limit: int = 20) -> list[dict] | None:
    """公司公告"""
    try:
        df = ak.stock_notice_report(symbol=symbol)
        if df is None or df.empty:
            return None
        recent = df.head(limit)
        return [
            {"title": str(row.get("公告标题", "")), "date": str(row.get("公告日期", ""))}
            for _, row in recent.iterrows()
        ]
    except Exception:
        return None
