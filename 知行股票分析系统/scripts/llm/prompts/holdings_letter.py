"""
持仓日报 prompt — 分析师口吻，给出持仓状态总结 + 次日建议
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(holdings_data: list, date_str: str = "") -> list:
    """构建持仓日报 messages
    holdings_data: [{"code":, "name":, "qty":, "cost":, "last":, "change_pct":,
                     "J":, "RSI":, "趋势":, "评分":, "信号":[], "B1_active":,
                     "near_B1":, "超缩量":, "status_change":, ...}, ...]
    """
    pos_lines = []
    for h in holdings_data:
        pnl_pct = ((h.get("last", 0) - h.get("cost", 0)) / h.get("cost", 1) * 100) if h.get("cost") else 0
        b1_status = "B1 活跃" if h.get("B1_active") else ("近B1" if h.get("near_B1") else "—")
        change_note = h.get("status_change", "") or "—"
        pos_lines.append(
            f"| {h.get('name','?')}({h.get('code','?')}) | {h.get('qty','?')}股 | "
            f"成本{h.get('cost','?')} | 现价{h.get('last','?')} | "
            f"{h.get('change_pct',0):+.2f}% | 浮{('盈' if pnl_pct >= 0 else '亏')}{abs(pnl_pct):.1f}% | "
            f"J={h.get('J','?')} | {h.get('趋势','?')} | {b1_status} | {change_note} |"
        )
    pos_table = "\n".join(pos_lines) if pos_lines else "（无持仓）"

    user_msg = f"""请基于以下持仓数据，生成今日的持仓日报。

日期：{date_str or "今日"}

## 持仓状态

| 名称代码 | 数量 | 成本 | 现价 | 日涨跌 | 浮动盈亏 | J值 | 趋势 | B1状态 | 变化 |
|----------|------|------|------|--------|----------|-----|------|--------|------|
{pos_table}

## 输出要求

请按以下结构输出（Markdown 格式）：

### 今日持仓概览
一句话总结今日持仓整体表现（涨多还是跌多？有没有异动？）

### 各股点评
对每只持仓股做 1-2 句话点评：
- 技术面变化（J值/趋势/B1 信号的变化）
- 与昨日对比的变化（如有）

### 明日关注
对明天的操作提出关注要点：
- 哪些持仓需要重点关注（信号变化/临界点）
- 是否有加仓/减仓/观望的技术依据
- 具体的关注价位和条件

不构成投资建议，仅供技术面参考。直接输出分析内容，不要加一级标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
