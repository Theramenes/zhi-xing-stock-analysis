"""
板块叙事分析 prompt — 把 SectorB1Result 批量数据喂给 LLM，生成板块情绪/B1 密度解读
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE


def build_prompt(sector_name: str, b1_data: dict) -> list:
    """构建板块叙事分析 messages"""
    stocks = b1_data.get("stocks", [])
    total = len(stocks)

    b1_list = [s for s in stocks if (s.get("信号") or s.get("基础B1") or s.get("基础B2"))]
    near_list = [s for s in stocks if not (s.get("信号") or s.get("基础B1")) and s.get("J", 999) < 20]
    trend_hold = [s for s in stocks if s.get("评分", 0) >= 3 and "多头" in str(s.get("趋势", ""))
                  and s not in b1_list and s not in near_list]
    suo_list = [s for s in stocks if s.get("超缩量")]

    # 构建 B1 标列表
    b1_lines = []
    for s in b1_list[:15]:
        sig_str = "+".join(s.get("信号", []))
        b1_lines.append(
            f"| {s.get('name','?')}({s.get('code','?')}) | "
            f"{s.get('close', s.get('last','?'))} | "
            f"{s.get('J','?')} | "
            f"{s.get('趋势','?')} | "
            f"{s.get('评分','?')} | "
            f"{sig_str} |"
        )
    b1_table = "\n".join(b1_lines) if b1_lines else "（暂无B1标的）"

    near_lines = []
    for s in near_list[:10]:
        near_lines.append(f"- {s.get('name','?')}({s.get('code','?')}) J={s.get('J','?')} 评分={s.get('评分','?')}")
    near_str = "\n".join(near_lines) if near_lines else "（暂无近B1标的）"

    trend_lines = []
    for s in trend_hold[:10]:
        trend_lines.append(f"- {s.get('name','?')}({s.get('code','?')}) 评分={s.get('评分','?')}")
    trend_str = "\n".join(trend_lines) if trend_lines else "（暂无趋势持有标的）"

    user_msg = f"""请分析「{sector_name}」板块的 B1 扫描结果。

## 板块概况
- 扫描成分股：{total} 只
- B1 信号标的：{len(b1_list)} 只
- 近 B1（J<20）：{len(near_list)} 只
- 趋势持有：{len(trend_hold)} 只
- 超缩量标的：{len(suo_list)} 只

## B1 信号标的一览
| 名称代码 | 收盘价 | J值 | 趋势 | 评分 | 信号 |
|----------|--------|-----|------|------|------|
{b1_table}

## 近 B1 观察区
{near_str}

## 趋势持有标段
{trend_str}

## 输出要求

请按以下结构输出（Markdown 格式）：

### 板块情绪
B1 密度（{len(b1_list)}/{total}）意味着什么？板块是处于普遍超卖还是只是个别现象？

### B1 标的质量评价
对 B1 标的中信号最强的 3-5 只做简要点评（信号组合含义、趋势配合度）

### 跨股模式
B1 标的之间有没有共同特征？（如同一细分行业、同样的信号组合、同样的趋势状态）

### 关注建议
投资者接下来应该重点关注什么？（哪些标的需要跟踪、哪些条件出现说明板块可能反转）

直接输出分析内容，不要加一级标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE},
        {"role": "user", "content": user_msg},
    ]
