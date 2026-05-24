"""
关注列表监控 prompt — 每日刷新关注列表时，把变化和状态总结成报告
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(watchlist_changes: dict, date_str: str = "") -> list:
    """构建关注列表监控 messages
    watchlist_changes: {
        "date": "2026-05-23",
        "active": [{code, name, J, 趋势, 评分, 信号[], B1_active, near_B1, close, change_pct, ...}],
        "changes": [{code, name, old_stage, new_stage, old_J, new_J, ...}],
        "new_B1": [{code, name, ...}],
        "b1_lost": [{code, name, ...}],
        "near_b1_new": [{code, name, J, ...}],
    }
    """
    date = watchlist_changes.get("date", date_str or "今日")
    active = watchlist_changes.get("active", [])
    changes = watchlist_changes.get("changes", [])
    new_b1 = watchlist_changes.get("new_B1", [])
    b1_lost = watchlist_changes.get("b1_lost", [])
    near_new = watchlist_changes.get("near_b1_new", [])

    active_lines = []
    for a in active[:30]:
        b1_status = "B1" if a.get("B1_active") else ("近B1" if a.get("near_B1") else "观察")
        sig = "+".join(a.get("信号", [])) or "—"
        active_lines.append(
            f"| {a.get('name','?')}({a.get('code','?')}) | {a.get('close','?')} | "
            f"{a.get('change_pct',0):+.2f}% | J={a.get('J','?')} | "
            f"{a.get('趋势','?')} | {a.get('评分','?')} | {b1_status} | {sig} |"
        )
    active_table = "\n".join(active_lines) if active_lines else "（无关注标的）"

    new_b1_str = ", ".join(f"{c.get('name','?')}({c.get('code','?')})" for c in new_b1) or "无"
    lost_str = ", ".join(f"{c.get('name','?')}({c.get('code','?')})" for c in b1_lost) or "无"
    near_str = ", ".join(f"{c.get('name','?')}({c.get('code','?')})" for c in near_new) or "无"

    change_lines = []
    for c in changes[:20]:
        change_lines.append(
            f"- {c.get('name','?')}({c.get('code','?')}): {c.get('old_stage','?')} → {c.get('new_stage','?')}, "
            f"J: {c.get('old_J','?')} → {c.get('new_J','?')}"
        )
    change_str = "\n".join(change_lines) if change_lines else "（今日无状态变化）"

    user_msg = f"""请基于以下关注列表数据，生成今日的关注列表监控报告。

日期：{date}

## 关注列表状态
| 名称代码 | 收盘价 | 涨跌 | J值 | 趋势 | 评分 | B1状态 | 信号 |
|----------|--------|------|-----|------|------|--------|------|
{active_table}

## 今日变化
- 新进入 B1：{new_b1_str}
- B1 信号消失：{lost_str}
- 新进入近 B1：{near_str}

## 状态变化详情
{change_str}

## 输出要求

请按以下结构输出（Markdown 格式）：

### 关注列表概况
用 2-3 句话总结当前关注列表的整体状态（共 {len(active)} 只、B1 活跃几只、近 B1 几只、是否有值得警惕的变化）。

### 重点关注变化
分析今日最重要的变化（新进入 B1 和失去 B1 的标的），说明变化的技术含义。

### 明日跟踪建议
列出明天应该重点跟踪的 3-5 只标的及跟踪要点。

直接输出分析内容，不要加一级标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
