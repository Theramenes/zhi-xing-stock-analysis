"""
K线综合分析 Prompt — 形态 + 基本面 + 题材关联 + B1信号
"""
from llm.prompts import SYSTEM_PROMPT, B1_INDICATOR_GUIDE, CHIP_GUIDE


def build_prompt(name: str, code: str, kline_ctx: dict, fundamental_ctx: str = "",
                 theme_ctx: str = "", sector_ctx: str = "", chip_ctx: str = "",
                 news_ctx: str = "") -> list:
    """
    kline_ctx: preprocess_kline 输出
    fundamental_ctx: 基本面数据文本
    theme_ctx: 题材/产业链分析文本
    sector_ctx: 板块定位文本
    chip_ctx: 筹码数据文本
    news_ctx: 近期消息文本
    """
    kline_table = kline_ctx.get("kline_table", "")
    patterns = kline_ctx.get("patterns", [])
    vol = kline_ctx.get("volume_analysis", {})
    price = kline_ctx.get("price_structure", {})
    ma = kline_ctx.get("ma_context", {})
    b1 = kline_ctx.get("b1_context", {})

    pattern_str = "\n".join(f"- {p}" for p in patterns) if patterns else "无明显形态信号"

    user_msg = f"""请对 {name}({code}) 做一次综合技术分析。

## K线数据（最近{kline_ctx.get('n_days','?')}日）
```
{kline_table}
```

## K线形态识别（系统预处理）
{pattern_str}

## 量能分析
- 5日均量: {vol.get('volume_5d_avg','?')} | 10日均量: {vol.get('volume_10d_avg','?')}
- 量能状态: {vol.get('status','?')}
- 量能趋势: {vol.get('trend','?')}
- 换手率: {vol.get('latest_turnover','?')}% {vol.get('turnover_note','')}

## 价格结构
- 10日区间: {price.get('low_10d','?')} - {price.get('high_10d','?')}
- 当前处于区间: {price.get('position_in_range','?')} 位置
- 5日涨跌: {price.get('change_5d','?')} | 10日涨跌: {price.get('change_10d','?')}

## 趋势指标
- 白线(短期): {ma.get('白线(短期趋势)','?')} {ma.get('白线方向','?')} | 黄线(中期): {ma.get('黄线(中期趋势)','?')} {ma.get('黄线方向','?')}
- 趋势状态: {ma.get('趋势','?')} | 强趋势: {ma.get('强趋势股',False)} | 做上涨趋势: {ma.get('做上涨趋势',False)}
- BBI: {ma.get('BBI','?')} | 转势风险: {ma.get('转势',False)}

## B1指标状态
- J值: {b1.get('J值','?')} {b1.get('J方向','?')} | K/D: {b1.get('K','?')}/{b1.get('D','?')}
- RSI: {b1.get('RSI','?')} | 评分: {b1.get('评分','?')}/5
- B1信号: {', '.join(b1.get('B1信号',[])) or '无'} | B1/B2/B3: {b1.get('基础B1/B2/B3','?')}
- 缩量: {b1.get('缩量状态','?')} | 单针下20: {b1.get('单针下20',False)}
- ⚠️: 死叉={b1.get('死叉',False)} 破线={b1.get('破线',False)}

{fundamental_ctx}
{theme_ctx}
{sector_ctx}
{chip_ctx}
{news_ctx}

## 分析要求

请从以下维度综合分析（Markdown 格式）：

### 一、K线形态解读
- 最近几日的K线组合传达了什么信号？（从形态识别结果中解读）
- 多空力量对比如何？（结合实体大小、影线长度、量能配合）
- 是否存在关键形态？（突破/破位/反转信号/持续形态）

### 二、量价关系
- 量能与价格走势是否配合？（价升量增=健康，价跌量缩=正常回调，放量下跌=警惕）
- 换手率水平意味着什么？
- 量能变化趋势预示什么？

### 三、B1信号与趋势研判
- 当前B1信号与K线形态是否相互印证？
- J值方向 + 白黄线方向 + K线形态，三者能否形成一致判断？
- 如果B1信号出现，K线形态是否支持入场？

### 四、题材与基本面交叉判断
- 结合基本面和题材，当前K线走势是否合理？
- 题材热度是否足以支撑技术面的信号？

### 五、综合结论
- 一句话总结当前技术状态
- 给出2-3个需要持续跟踪的关键条件（如"放量突破X元确认"、"缩量回踩X元获得支撑"）

不构成投资建议。直接输出分析，不用加总标题。"""
    return [
        {"role": "system", "content": SYSTEM_PROMPT + "\n\n" + B1_INDICATOR_GUIDE + "\n\n" + CHIP_GUIDE},
        {"role": "user", "content": user_msg},
    ]
