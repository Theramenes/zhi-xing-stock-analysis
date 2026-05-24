"""
个股深度分析 prompt — 股票逻辑 + 板块定位 + 横向对比 + 市场叙事
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(code: str, name: str, indicators: dict,
                 sector_context: dict = None) -> list:
    """
    indicators: b1_calculator 输出
    sector_context: {"name": str, "rank": str, "change_pct": float, "fund_flow": str,
                     "total_stocks": int, "b1_density": str,
                     "top_peers": [{"code","name","J","评分","信号[]","趋势"}],
                     "market_context": {"top_sectors": [...], "market_breadth": str}
                    }
    """
    j_val = indicators.get("J", "?")
    rsi = indicators.get("RSI", "?")
    trend = indicators.get("趋势", "?")
    white = indicators.get("白线", "?")
    yellow = indicators.get("黄线", "?")
    bbi = indicators.get("BBI", "?")
    score = indicators.get("评分", "?")
    signals = indicators.get("信号", [])
    last_price = indicators.get("last", "?")
    change = indicators.get("change_pct", 0)
    b1 = indicators.get("基础B1", False)
    b2 = indicators.get("基础B2", False)
    b3 = indicators.get("基础B3", False)
    suo_extreme = indicators.get("超缩量", False)
    suo_ok = indicators.get("适当缩量", False)
    zhen20 = indicators.get("单针下20", False)
    wash = indicators.get("洗盘异动", False)
    dead_cross = indicators.get("死叉", False)
    break_line = indicators.get("破线", False)
    trend_reverse = indicators.get("转势", False)
    dist_white = indicators.get("距离白线_pct", 0)
    dist_yellow = indicators.get("距离黄线_pct", 0)
    is_bull = "多头" in str(trend)

    # ==== 股票自身指标表 ====
    indicator_table = f"""| 指标 | 数值 | 解读 |
|------|------|------|
| 最新价 | {last_price} | 涨跌 {change:+.1f}% |
| J 值 | {j_val} | {"超卖(<20)" if isinstance(j_val, (int, float)) and j_val < 20 else "正常偏高" if isinstance(j_val, (int, float)) and j_val > 80 else "正常"} |
| RSI | {rsi} | {"超买" if isinstance(rsi, (int, float)) and rsi > 70 else "超卖" if isinstance(rsi, (int, float)) and rsi < 30 else "正常"} |
| 趋势 | {trend} | {"多头排列" if is_bull else "空头"} |
| 白线 | {white} | 短期趋势支撑 |
| 黄线 | {yellow} | 中期趋势支撑 |
| BBI | {bbi} | 多空分界线 |
| 评分 | {score}/5 | |
| 距离白线 | {dist_white:.1f}% | |
| 距离黄线 | {dist_yellow:.1f}% | |

信号: {", ".join(signals) if signals else "无"}
B1/B2/B3: {"✓" if b1 else "✗"}/{"✓" if b2 else "✗"}/{"✓" if b3 else "✗"}
超缩量: {"是" if suo_extreme else "适当缩量" if suo_ok else "否"}
单针下20: {"是" if zhen20 else "否"}
洗盘异动: {"是" if wash else "否"}
死叉/破线/转势: {"⚠️" if dead_cross else "✓"}/{"⚠️" if break_line else "✓"}/{"⚠️" if trend_reverse else "✓"}
"""

    # ==== 板块上下文 ====
    sector_block = ""
    if sector_context:
        sc = sector_context
        peers_block = ""
        if sc.get("top_peers"):
            peer_lines = []
            for p in sc["top_peers"][:8]:
                sig = "+".join(p.get("信号", [])) or "—"
                peer_lines.append(
                    f"| {p.get('name','?')}({p.get('code','?')}) | "
                    f"J={p.get('J','?')} | {p.get('评分','?')}分 | "
                    f"{p.get('趋势','?')} | {sig} |"
                )
            peers_block = """## 同板块核心标的 B1 对比

| 名称代码 | J值 | 评分 | 趋势 | 信号 |
|----------|-----|------|------|------|
""" + "\n".join(peer_lines)

        sector_block = f"""
## 板块背景

- 板块：{sc.get("name", "?")}
- 板块排名：{sc.get("rank", "?")}
- 板块涨跌：{sc.get("change_pct", 0):+.2f}%
- 资金流向：{sc.get("fund_flow", "?")}
- 成分股数：{sc.get("total_stocks", "?")} 只
- B1 密度：{sc.get("b1_density", "?")}

{peers_block}

## 市场环境

- 领涨板块：{sc.get("market_context", {}).get("top_sectors", "?")}
- 市场宽度：{sc.get("market_context", {}).get("market_breadth", "?")}
"""

    user_msg = f"""请对 {name}（{code}）做一次深度分析。你需要从三个层次来理解这只股票：

## 第一层：个股逻辑
{indicator_table}

## 第二层：板块定位
{sector_block if sector_block else "（未提供板块数据，请仅基于第一层分析）"}

## 输出要求

请以三层结构输出（Markdown）：

### 一、个股技术逻辑
- 当前技术状态的核心矛盾是什么？
- 为什么会出现这样的技术状态？（从趋势、量能、信号三个角度解释）
- 后续可能的演变路径（2-3 种情景）

### 二、板块定位与横向对比
- 这只票在板块中处于什么位置？（领涨/跟涨/补涨/滞涨/领跌）
- 与同板块其他 B1 标段相比，信号质量和趋势配合度如何？
- 该板块当前处于什么阶段？（主线主升/主线回踩/轮动补涨/退潮）

### 三、大局研判
- 结合板块热度和市场环境，当前最合理的策略是什么？
- 如果板块是主线，这只票是核心标的还是边缘标的？
- 如果板块在回踩，这只票是否具备承接条件（回踩支撑位+缩量+J值收敛）？
- 列出未来 1-2 周需要重点跟踪的 3 个关键条件

不构成投资建议。直接输出三层分析，不要重复标题之外的任何内容。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
