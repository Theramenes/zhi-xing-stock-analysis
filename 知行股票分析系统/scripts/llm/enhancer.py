"""
报告增强器 — 将现有指标数据喂给 LLM，生成自然语言解读
"""
import hashlib
import json
import time
from datetime import datetime

from llm.client import chat
from config.llm_config import get_llm_config


def _save_llm_report(report_type: str, code: str | None, input_data: dict,
                     content: str, model: str, tokens_in: int, tokens_out: int, elapsed: float):
    """保存 LLM 生成结果到 SQLite"""
    from storage.db import get_db
    db = get_db()
    db.conn.execute(
        """INSERT INTO llm_report (code, report_type, query_date, prompt_hash,
           raw_input, content, model, tokens_in, tokens_out, elapsed_sec, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (code or "", report_type, datetime.now().strftime("%Y-%m-%d"),
         hashlib.md5(json.dumps(input_data, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16],
         json.dumps(input_data, ensure_ascii=False, default=str)[:8000],
         content, model, tokens_in, tokens_out, round(elapsed, 2),
         datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    )
    db.conn.commit()


def _run_llm(messages: list, report_type: str, code: str | None, input_data: dict) -> str | None:
    """调用 LLM 并保存结果。未配置 LLM 时返回 None。"""
    config = get_llm_config()
    if not config.available:
        return None

    start = time.time()
    resp = chat(messages)
    if not resp:
        return None
    elapsed = time.time() - start
    try:
        _save_llm_report(
            report_type=report_type, code=code, input_data=input_data,
            content=resp["content"], model=resp.get("model", config.model),
            tokens_in=resp.get("tokens_in", 0), tokens_out=resp.get("tokens_out", 0),
            elapsed=elapsed,
        )
    except Exception:
        pass  # 保存失败不影响主流程
    return resp["content"]


# ============================================================
# 对外接口
# ============================================================

def enhance_stock_deep(code: str, name: str, indicators: dict,
                       sector_context: dict = None) -> str | None:
    """个股深度分析（三层：个股逻辑 + 板块定位 + 大局研判）"""
    messages = __import__("llm.prompts.stock_deep", fromlist=["build_prompt"]).build_prompt(
        code, name, indicators, sector_context
    )
    content = _run_llm(messages, "stock_deep", code, indicators)
    if not content:
        return None
    return f"## AI 深度分析\n\n{content}\n"

def enhance_stock_report(code: str, name: str, indicators: dict) -> str | None:
    """
    个股技术解读
    Returns: Markdown 字符串（含 "## AI 技术解读" 标题），或 None（LLM 未配置）
    """
    messages = __import__("llm.prompts.stock_analysis", fromlist=["build_prompt"]).build_prompt(code, name, indicators)
    content = _run_llm(messages, "stock", code, indicators)
    if not content:
        return None
    return f"## AI 技术解读\n\n{content}\n"


def enhance_sector_report(sector_name: str, b1_data: dict) -> str | None:
    """
    板块叙事分析
    Returns: Markdown 字符串（含 "## AI 板块叙事" 标题），或 None
    """
    messages = __import__("llm.prompts.sector_narrative", fromlist=["build_prompt"]).build_prompt(sector_name, b1_data)
    content = _run_llm(messages, "sector", None, {"sector": sector_name, "b1_summary": {
        "total": len(b1_data.get("stocks", [])),
        "b1_count": len(b1_data.get("b1_stocks", [])),
        "near_count": len(b1_data.get("near_b1_stocks", [])),
    }})
    if not content:
        return None
    return f"## AI 板块叙事\n\n{content}\n"


def generate_holdings_letter(holdings_data: list) -> str | None:
    """
    持仓日报（分析师口吻 + 次日建议）
    Returns: 完整 Markdown 文档，或 None
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    messages = __import__("llm.prompts.holdings_letter", fromlist=["build_prompt"]).build_prompt(holdings_data, date_str)
    content = _run_llm(messages, "holdings", None, {"holdings": [
        {"code": h.get("code"), "J": h.get("J"), "趋势": h.get("趋势"), "评分": h.get("评分")}
        for h in holdings_data
    ]})
    if not content:
        return None
    return f"# 持仓日报 — {date_str}\n\n{content}\n"


def generate_holdings_review(raw_data: dict) -> str | None:
    """
    持仓复盘/监控报告
    raw_data: {"mode": "review"|"monitor", "date": ..., "active": [...], "closed": [...], ...}
    Returns: 完整 Markdown 文档，或 None
    """
    date_str = raw_data.get("date", datetime.now().strftime("%Y-%m-%d"))
    mode = raw_data.get("mode", "review")
    messages = __import__("llm.prompts.holdings_review", fromlist=["build_prompt"]).build_prompt(raw_data)
    content = _run_llm(messages, "holdings_review", None, {
        "mode": mode,
        "date": date_str,
        "active_count": len(raw_data.get("active", [])),
        "closed_count": len(raw_data.get("closed", [])),
    })
    if not content:
        return None
    title = "持仓复盘" if mode == "review" else "持仓监控"
    return f"# {title} — {date_str}\n\n{content}\n"


def generate_watchlist_report(watchlist_changes: dict) -> str | None:
    """
    关注列表监控报告
    Returns: 完整 Markdown 文档，或 None
    """
    date_str = datetime.now().strftime("%Y-%m-%d")
    messages = __import__("llm.prompts.watchlist_report", fromlist=["build_prompt"]).build_prompt(
        watchlist_changes, date_str
    )
    content = _run_llm(messages, "watchlist", None, {"changes_summary": {
        "active_count": len(watchlist_changes.get("active", [])),
        "new_b1": [c.get("code") for c in watchlist_changes.get("new_B1", [])],
        "b1_lost": [c.get("code") for c in watchlist_changes.get("b1_lost", [])],
    }})
    if not content:
        return None
    return f"# 关注列表监控 — {date_str}\n\n{content}\n"


def diagnose_trade(code: str, name: str, action: str, shares: int,
                   stock_indicators: dict, holdings_ctx: str = "") -> str | None:
    """
    交易诊断
    Returns: Markdown 字符串（含 "## 交易诊断" 标题），或 None
    """
    messages = __import__("llm.prompts.trade_diagnosis", fromlist=["build_prompt"]).build_prompt(
        code, name, action, shares, stock_indicators, holdings_ctx
    )
    content = _run_llm(messages, "trade", code, {"action": action, "shares": shares,
                                                    "indicators_summary": {
                                                        "趋势": stock_indicators.get("趋势"),
                                                        "J": stock_indicators.get("J"),
                                                        "评分": stock_indicators.get("评分"),
                                                    }})
    if not content:
        return None
    return f"## 交易诊断\n\n{content}\n"
