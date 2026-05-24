"""
个股技术解读 prompt — 把 b1_calculator 输出的指标 JSON 翻译成"人话版"技术诊断
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(code: str, name: str, indicators: dict) -> list:
    """构建个股技术解读 messages"""
    # 提取关键字段
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
    suo = indicators.get("缩量", False)
    suo_ok = indicators.get("适当缩量", False)
    suo_extreme = indicators.get("超缩量", False)
    zhen20 = indicators.get("单针下20", False)
    double_zero = indicators.get("双线归零", False)
    wash = indicators.get("洗盘异动", False)
    dead_cross = indicators.get("死叉", False)
    break_line = indicators.get("破线", False)
    trend_reverse = indicators.get("转势", False)
    dist_white = indicators.get("距离白线_pct", 0)
    dist_yellow = indicators.get("距离黄线_pct", 0)
    vol_up = indicators.get("放量下跌", False)
    is_bull = "多头" in str(trend)
    is_bear = "空头" in str(trend)

    user_msg = f"""请分析 {name}（{code}）的当前技术状态。

## 指标数据

| 指标 | 数值 | 说明 |
|------|------|------|
| 最新价 | {last_price} | 涨跌幅 {change:+.1f}% |
| J 值 | {j_val} | {"超卖区(<-15)" if isinstance(j_val, (int, float)) and j_val < -15 else "超卖区(<20)" if isinstance(j_val, (int, float)) and j_val < 20 else "正常"} |
| RSI | {rsi} | |
| 趋势 | {trend} | {"多头" if is_bull else "空头" if is_bear else "震荡"} |
| 白线 | {white} | 短期趋势线 |
| 黄线 | {yellow} | 中期趋势线 |
| BBI | {bbi} | 多空分界线 |
| 综合评分 | {score}/5 | |
| 距离白线 | {dist_white:.1f}% | |
| 距离黄线 | {dist_yellow:.1f}% | |

## 信号状态

| 信号 | 状态 |
|------|------|
| B1 信号 | {", ".join(signals) if signals else "无"} |
| 基础B1/B2/B3 | {"✓" if b1 else "✗"} / {"✓" if b2 else "✗"} / {"✓" if b3 else "✗"} |
| 缩量 | {"超缩量" if suo_extreme else "适当缩量" if suo_ok else "缩量" if suo else "—"} |
| 单针下20 | {"✓" if zhen20 else "✗"} |
| 双线归零 | {"✓" if double_zero else "✗"} |
| 洗盘异动 | {"✓" if wash else "✗"} |
| 死叉 | {"✓ 警惕" if dead_cross else "✗"} |
| 破线 | {"✓ 警惕" if break_line else "✗"} |
| 转势 | {"✓ 警惕" if trend_reverse else "✗"} |
| 放量下跌 | {"✓ 警惕" if vol_up else "✗"} |

## 输出要求

请按以下结构输出分析（Markdown 格式）：

### 技术诊断
用 2-3 句话概括当前技术状态的核心矛盾。例如："这只票 J 值已进入超卖区且出现拐头B信号，但趋势仍为空头，需要等待趋势确认。"

### 信号解读
逐一解读当前激活的信号含义，以及这些信号组合在一起意味着什么。如果没有任何信号，说明为什么当前不符合 B1 条件。

### 关键价位
明确给出：支撑位（白线/黄线/BBI）、压力位、当前价格所处位置

### 操作参考
- 如果是空仓者，当前技术面应该关注什么？
- 如果已持仓，当前技术面提示关注什么风险？
- 不构成投资建议，仅供技术面参考

直接输出分析内容，不要加一级标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
