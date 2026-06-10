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


# ════════════════════════════════════════════════════════════
# 周末外环境多维度搜索
# ════════════════════════════════════════════════════════════

_WEEKEND_DOMAINS = [
    "reuters.com", "bloomberg.com", "cnbc.com", "wsj.com",
    "finance.sina.com.cn", "eastmoney.com", "cls.cn", "caixin.com",
    "yicai.com", "ftchinese.com", "wallstreetcn.com",
]


def _search_dimension(query: str, label: str, max_results: int = 5, days: int = 7) -> tuple:
    """搜索一个维度，返回 (label, text)。"""
    text = search_context(query, max_results=max_results, days=days)
    return (label, text or "(无结果)")


def search_global_macro(days: int = 7) -> tuple:
    """全球宏观：美联储/欧央行/通胀/GDP/利率"""
    return _search_dimension(
        "美联储 利率 通胀 CPI 非农 全球宏观经济 2026",
        "全球宏观", max_results=6, days=days
    )


def search_geopolitical(days: int = 7) -> tuple:
    """地缘政治：中美关系/贸易战/科技制裁/台海"""
    return _search_dimension(
        "中美关系 贸易战 关税 芯片制裁 地缘政治 台海 2026",
        "地缘政治", max_results=6, days=days
    )


def search_global_markets(days: int = 5) -> tuple:
    """全球市场：美股/港股/商品/外汇"""
    return _search_dimension(
        "美股 S&P500 NASDAQ 港股 恒生 黄金 原油 人民币汇率 2026",
        "全球市场", max_results=6, days=days
    )


def search_a_share_policy(days: int = 7) -> tuple:
    """A股政策面：证监会/央行/产业政策/新规"""
    return _search_dimension(
        "证监会 央行 中国 降准 降息 印花税 产业政策 A股 改革 2026",
        "国内政策", max_results=6, days=days
    )


def search_sector_catalysts(days: int = 7) -> tuple:
    """行业催化：科技/新能源/医药/消费/周期"""
    return _search_dimension(
        "A股 行业催化剂 半导体 新能源 医药 消费 人工智能 政策利好 2026",
        "行业催化", max_results=8, days=days
    )


def search_weekend_headlines(days: int = 3) -> tuple:
    """周末突发/头条（短期，2-3天）"""
    return _search_dimension(
        "周末 重大新闻 A股 利好 利空 突发 2026",
        "周末要闻", max_results=8, days=days
    )


def run_weekend_news_sweep(days: int = 7) -> dict:
    """
    周末外环境全景搜索。
    Returns: {"dim_key": (label, text), ...}
    """
    import concurrent.futures
    dimensions = {
        "macro": lambda: search_global_macro(days),
        "geopolitical": lambda: search_geopolitical(days),
        "global_markets": lambda: search_global_markets(max(3, days - 2)),
        "policy": lambda: search_a_share_policy(days),
        "catalysts": lambda: search_sector_catalysts(days),
        "weekend": lambda: search_weekend_headlines(3),
    }
    results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = {ex.submit(fn): key for key, fn in dimensions.items()}
        for fut in concurrent.futures.as_completed(futures):
            key = futures[fut]
            try:
                results[key] = fut.result()
            except Exception as e:
                results[key] = (key, f"(搜索失败: {e})")
    return results
