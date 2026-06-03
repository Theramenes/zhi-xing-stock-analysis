"""
Tavily Web Search — LLM Background Context 数据源

环境变量: TAVILY_API_KEY
"""
import os
import time
from typing import Optional, List, Dict


def _get_client():
    token = os.environ.get("TAVILY_API_KEY", "").strip()
    if not token:
        return None
    try:
        from tavily import TavilyClient
        return TavilyClient(api_key=token)
    except ImportError:
        return None
    except Exception:
        return None


def search_context(query: str, max_results: int = 5, days: int = 7) -> Optional[str]:
    """搜索最新信息，返回拼接好的 LLM 上下文文本。"""
    client = _get_client()
    if not client:
        return None
    try:
        resp = client.search(
            query, search_depth="advanced", max_results=max_results,
            include_answer=True, include_raw_content=False, days=days
        )
        results = resp.get("results", [])
        if not results:
            return None
        lines = []
        for r in results:
            title = r.get("title", "")
            url = r.get("url", "")
            content = (r.get("content", "") or "")[:300]
            lines.append(f"- [{title}]({url}): {content}")
        answer = resp.get("answer", "")
        if answer:
            lines.insert(0, f"**摘要**: {answer}")
        return "\n".join(lines)
    except Exception:
        return None


def get_market_news() -> Optional[str]:
    """今日A股市场热点/主线/政策"""
    return search_context("A股 今日热点 主线 资金流向 政策 2026", max_results=8, days=2)


def get_sector_news(sector: str) -> Optional[str]:
    """指定板块最新消息"""
    return search_context(f"{sector} 板块 A股 政策 投资 2026", max_results=5, days=3)


def get_stock_news(code_or_name: str) -> Optional[str]:
    """指定股票最新消息"""
    return search_context(f"{code_or_name} 股票 利好消息 2026", max_results=3, days=7)


def get_theme_context(theme: str) -> Optional[str]:
    """主线题材逻辑背景"""
    return search_context(f"{theme} A股 产业链 投资逻辑 2026", max_results=5, days=7)
