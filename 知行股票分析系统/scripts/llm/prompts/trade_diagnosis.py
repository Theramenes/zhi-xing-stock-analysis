"""
交易诊断 prompt — 用户输入买卖意图，LLM 从 6 维度检查
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(code: str, name: str, action: str, shares: int,
                 stock_indicators: dict, holdings_ctx: str = "") -> list:
    """构建交易诊断 messages"""
    trend = stock_indicators.get("趋势", "?")
    j_val = stock_indicators.get("J", "?")
    score = stock_indicators.get("评分", "?")
    signals = stock_indicators.get("信号", [])
    last = stock_indicators.get("last", "?")
    white = stock_indicators.get("白线", "?")
    yellow = stock_indicators.get("黄线", "?")
    b1_active = bool(signals or stock_indicators.get("基础B1"))
    suo_extreme = stock_indicators.get("超缩量", False)
    dead_cross = stock_indicators.get("死叉", False)
    break_line = stock_indicators.get("破线", False)
    dist_white = stock_indicators.get("距离白线_pct", 0)

    action_cn = "买入" if action == "buy" else "卖出" if action == "sell" else action
    risk_checks = []
    if "空头" in str(trend):
        risk_checks.append("- ⚠️ 趋势为空头，逆势操作风险较高")
    if dead_cross:
        risk_checks.append("- ⚠️ 存在死叉信号")
    if break_line:
        risk_checks.append("- ⚠️ 价格已跌破关键支撑线")

    user_msg = f"""请对以下交易意图进行 6 维度系统诊断。

## 交易意图
- 股票：{name}（{code}）
- 操作：{action_cn}
- 数量：{shares} 股
- 当前价：{last}

## 技术指标
| 指标 | 数值 |
|------|------|
| 趋势 | {trend} |
| J 值 | {j_val} |
| 综合评分 | {score}/5 |
| B1 信号 | {", ".join(signals) if signals else "无"} |
| 白线 | {white} |
| 黄线 | {yellow} |
| 距离白线 | {dist_white:.2%} |
| 超缩量 | {"是" if suo_extreme else "否"} |
| 死叉 | {"是" if dead_cross else "否"} |
| 破线 | {"是" if break_line else "否"} |

{holdings_ctx}

## 输出要求

请从以下 6 个维度逐一诊断，每个维度给出 ✅（通过）/ ⚠️（警告）/ ❌（否决）：

1. **价值维度**：当前价格是否在合理的技术区间？（结合 B1 信号、白黄线位置）
2. **仓位维度**：当前持仓与计划加仓后的仓位是否合理？
3. **时机维度**：当前技术信号是否支持此时操作？（J 值位置、趋势方向、信号状态）
4. **市场维度**：趋势环境是否配合此操作方向？
5. **板块维度**：从技术面角度评估该股所处位置
6. **结论**：给出综合判断（可操作 / 观望 / 建议放弃）及理由

{"## 已有风险提示" if risk_checks else ""}
{chr(10).join(risk_checks) if risk_checks else ""}

不构成投资建议，仅供技术面诊断参考。直接输出诊断内容，不要加一级标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
