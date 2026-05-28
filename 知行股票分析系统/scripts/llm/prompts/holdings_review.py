"""
持仓复盘/监控 prompt — 把 raw data 输出给 LLM 做解读
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(raw_data: dict) -> list:
    """构建持仓复盘/监控 messages
    raw_data: {
        "mode": "review" | "monitor",
        "date": "2026-05-28",
        "active": [...],       # 当前持仓，每项含 code/name/qty/cost/last/change_pct/J/RSI/趋势/评分/B1_active/near_B1
        "closed": [...],       # 今日已清仓（review模式），每项含 code/name/archived_qty/avg_cost/closed_price/realized_pnl/realized_pnl_pct/change_pct
        "changes": [...],      # 调仓对比（review模式），每项含 code/name/action/start_qty/close_qty/old_cost/new_cost
        "transactions": [...], # 交易流水（review模式），每项含 code/name/direction/qty/price/reason
    }
    """
    mode = raw_data.get("mode", "review")
    date_str = raw_data.get("date", "")

    # 活跃持仓表
    active_lines = []
    for h in raw_data.get("active", []):
        pnl_pct = ((h.get("last", 0) - h.get("cost", 0)) / h.get("cost", 1) * 100) if h.get("cost") else 0
        b1_status = "B1活跃" if h.get("B1_active") else ("近B1" if h.get("near_B1") else "—")
        active_lines.append(
            f"| {h.get('name','?')}({h.get('code','?')}) | {h.get('qty','?')}股 | "
            f"成本{h.get('cost','?')} | 现价{h.get('last','?')} | "
            f"{h.get('change_pct',0):+.2f}% | 浮{('盈' if pnl_pct >= 0 else '亏')}{abs(pnl_pct):.1f}% | "
            f"J={h.get('J','?')} | {h.get('趋势','?')} | {b1_status} |"
        )
    active_table = "\n".join(active_lines) if active_lines else "（无持仓）"

    # 已清仓表（review模式）
    closed_table = ""
    if mode == "review" and raw_data.get("closed"):
        closed_lines = []
        for c in raw_data["closed"]:
            pnl = c.get("realized_pnl", 0) or 0
            pnl_pct = c.get("realized_pnl_pct", 0) or 0
            closed_lines.append(
                f"| {c.get('name','?')}({c.get('code','?')}) | {c.get('archived_qty','?')}股 | "
                f"成本{c.get('avg_cost','?')} | 清仓价{c.get('closed_price','?')} | "
                f"{'盈' if pnl >= 0 else '亏'}{abs(pnl):.1f} ({pnl_pct:+.1f}%) | "
                f"今日{c.get('change_pct',0):+.2f}% |"
            )
        closed_table = "\n".join(closed_lines)

    # 调仓对比（review模式）
    changes_text = ""
    if mode == "review" and raw_data.get("changes"):
        changes_lines = []
        for ch in raw_data["changes"]:
            action = ch.get("action", "?")
            code = ch.get("code", "?")
            name = ch.get("name", "?")
            start = ch.get("start_qty", 0)
            close = ch.get("close_qty", 0)
            old_c = ch.get("old_cost")
            new_c = ch.get("new_cost")
            cost_str = ""
            if old_c is not None and new_c is not None:
                cost_str = f"，成本 {old_c:.3f} → {new_c:.3f}"
            elif new_c is not None:
                cost_str = f"，最新成本 {new_c:.3f}"
            changes_lines.append(f"- {action} {name}({code}): {start}股 → {close}股{cost_str}")
        changes_text = "\n".join(changes_lines)

    # 交易流水（review模式）
    tx_text = ""
    if mode == "review" and raw_data.get("transactions"):
        tx_lines = []
        for t in raw_data["transactions"]:
            tx_lines.append(
                f"- {t.get('name','?')}({t.get('code','?')}) {t.get('direction','?')} "
                f"{t.get('qty','?')}股 @ {t.get('price','?')} "
                f"({t.get('reason','') or '无理由'})"
            )
        tx_text = "\n".join(tx_lines)

    if mode == "review":
        user_msg = f"""请基于以下今日持仓与交易数据，生成一份操作复盘报告。

日期：{date_str}

## 当前持仓状态

| 名称代码 | 数量 | 成本 | 现价 | 日涨跌 | 浮动盈亏 | J值 | 趋势 | B1状态 |
|----------|------|------|------|--------|----------|-----|------|--------|
{active_table}

## 今日已清仓

| 名称代码 | 清仓前数量 | 成本 | 清仓价 | 实现盈亏 | 今日涨跌 |
|----------|-----------|------|--------|----------|----------|
{closed_table or "（无）"}

## 今日调仓变动

{changes_text or "（无调仓）"}

## 今日交易流水

{tx_text or "（无交易）"}

## 输出要求

请按以下结构输出（Markdown 格式）：

### 今日操作总评
对今日整体操作给出 2-3 句话总结：仓位变化是否合理？实现盈亏是否符合预期？

### 各股操作复盘
对今日有变动的股票逐一点评：
- 买入/加仓：时机和价位评价，成本变化影响
- 卖出/减仓：离场时机评价，是否卖飞或逃顶
- 清仓：这笔持仓周期的总盈亏评价，操作得失

### 持仓健康度
对当前仍持有的股票做快速体检：有无异常信号？是否需要调整止损/目标？

### 明日关注
基于今天的操作结果，给出明天的关注要点和策略提醒。

不构成投资建议，仅供技术面复盘参考。直接输出分析内容，不要加一级标题。"""

    else:  # monitor 模式
        user_msg = f"""请基于以下当前持仓数据，生成持仓监控分析报告。

日期：{date_str}

## 当前持仓状态

| 名称代码 | 数量 | 成本 | 现价 | 日涨跌 | 浮动盈亏 | J值 | 趋势 | B1状态 |
|----------|------|------|------|--------|----------|-----|------|--------|
{active_table}

## 输出要求

请按以下结构输出（Markdown 格式）：

### 持仓概览
一句话总结当前持仓整体状态（仓位分布、盈亏分布、风险集中度）

### 各股监控点评
对每只持仓股做 1-2 句话技术面点评：
- J值/趋势/B1信号的变化
- 是否触及止损或目标价
- 是否需要重点关注

### 风险预警
列出需要警惕的信号：超缩量、趋势转弱、B1消失、J值过高等

### 操作建议
给出非强制性的关注建议：哪些票值得紧盯、哪些可以放宽观察频率

不构成投资建议，仅供技术面监控参考。直接输出分析内容，不要加一级标题。"""

    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
