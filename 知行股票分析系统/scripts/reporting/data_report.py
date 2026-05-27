"""
数据报告生成器 — 聚合 B1 指标 + 基本面 + 估值 + 消息 + 板块 + 市场
直接输出 Markdown，不走 LLM
"""
from datetime import datetime


def _fmt_direction(rising):
    """方向指示器"""
    if rising is None:
        return ""
    return "↑" if rising else "↓"


def _fmt(v, precision=2):
    """数字格式化"""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:.{precision}f}"
    return str(v)


def _fmt_pct(v):
    """百分比格式化"""
    if v is None:
        return "—"
    if isinstance(v, float):
        return f"{v:+.2f}%"
    return str(v)


def _fmt_amount(v):
    """金额格式化"""
    if v is None:
        return "—"
    if abs(v) >= 1e8:
        return f"{v/1e8:.2f}亿"
    if abs(v) >= 1e4:
        return f"{v/1e4:.0f}万"
    return f"{v:.2f}"


def build_individual_report(code: str, name: str, indicators: dict,
                            fundamentals: dict = None,
                            valuation: dict = None,
                            news_data: dict = None,
                            chip: dict = None,
                            fund_flow: dict = None,
                            market: dict = None,
                            sector_ctx: dict = None) -> str:
    """个股完整数据报告 → Markdown"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lines.append

    L(f"# {name}({code}) 数据报告")
    L(f"> {now}")
    L("")

    # ====== 1. B1 技术指标 ======
    _section_b1(lines, code, name, indicators)

    # ====== 2. 基本面 ======
    if fundamentals:
        _section_fundamentals(lines, fundamentals)
    else:
        L("## 基本面")
        L("*数据缺失*")
        L("")

    # ====== 3. 估值 ======
    if valuation and valuation.get("source") != "none":
        _section_valuation(lines, valuation)

    # ====== 4. 筹码 ======
    if chip:
        _section_chip(lines, chip)

    # ====== 5. 资金面 ======
    if fund_flow:
        _section_fund_flow(lines, fund_flow, indicators)

    # ====== 6. 消息面 ======
    if news_data:
        _section_news(lines, news_data)

    # ====== 7. 板块定位 ======
    if sector_ctx:
        _section_sector(lines, sector_ctx, code, name, indicators)

    # ====== 8. 市场大局 ======
    if market:
        _section_market(lines, market)

    L("---")
    L(f"*知行数据报告 {now}*")
    return "\n".join(lines)


def _section_b1(lines, code, name, indicators):
    L = lines.append
    L("## B1 技术指标")
    L("")
    j = indicators.get("J", "?")
    k_val = indicators.get("K", "?")
    d_val = indicators.get("D", "?")
    rsi = indicators.get("RSI", "?")
    trend = indicators.get("趋势", "?")
    white = indicators.get("白线", "?")
    yellow = indicators.get("黄线", "?")
    bbi = indicators.get("BBI", "?")
    score = indicators.get("评分", "?")
    last_price = indicators.get("last", "?")
    change = indicators.get("change_pct", 0)
    signals = indicators.get("信号", [])
    b1 = indicators.get("基础B1", False)
    b2 = indicators.get("基础B2", False)
    b3 = indicators.get("基础B3", False)
    suo_extreme = indicators.get("超缩量", False)
    suo_ok = indicators.get("适当缩量", False)
    zhen20 = indicators.get("单针下20", False)
    wash = indicators.get("洗盘异动", False)
    dead = indicators.get("死叉", False)
    bk = indicators.get("破线", False)
    rev = indicators.get("转势", False)
    strong_trend = indicators.get("强趋势股", False)
    uptrend = indicators.get("做上涨趋势", False)
    super_bull = indicators.get("超牛股", False)
    j_rising = indicators.get("J_rising")
    white_rising = indicators.get("白线_rising")
    yellow_rising = indicators.get("黄线_rising")
    white_cross = indicators.get("白线上穿黄线")
    white_cross_trend = indicators.get("白线上穿趋势")
    white_slope = indicators.get("白线斜率")
    yellow_slope = indicators.get("黄线斜率")
    dist_w = indicators.get("距离白线_pct", 0)
    dist_y = indicators.get("距离黄线_pct", 0)

    L(f"| 指标 | 数值 | 状态 |")
    L(f"|------|------|------|")
    L(f"| 最新价 | {_fmt(last_price)} | 涨跌 {_fmt_pct(change)} |")
    j_status = "超卖" if isinstance(j, (int, float)) and j < -15 else ("低位" if isinstance(j, (int, float)) and j < 20 else ("偏高" if isinstance(j, (int, float)) and j > 80 else "正常"))
    j_dir = _fmt_direction(j_rising)
    L(f"| J值 | {_fmt(j)} | {j_status} {j_dir} |")
    L(f"| K/D | {_fmt(k_val)} / {_fmt(d_val)} | |")
    L(f"| RSI | {_fmt(rsi)} | |")
    white_dir = _fmt_direction(white_rising)
    yellow_dir = _fmt_direction(yellow_rising)
    L(f"| 趋势白线 | {_fmt(white)} | {white_dir} (斜率{white_slope}) |" if white_slope else f"| 趋势白线 | {_fmt(white)} | {white_dir} |")
    L(f"| 大哥黄线 | {_fmt(yellow)} | {yellow_dir} (斜率{yellow_slope}) |" if yellow_slope else f"| 大哥黄线 | {_fmt(yellow)} | {yellow_dir} |")
    cross_str = ""
    if white_cross:
        cross_str = " ⚡白线上穿黄线(趋势反转信号)"
    elif white_cross_trend:
        cross_str = " ⚡白线上穿(备选检测)"
    L(f"| 趋势 | {trend} | 做上涨趋势={'✓' if uptrend else 'X'} 强趋势={'✓' if strong_trend else 'X'} 超牛={'✓' if super_bull else 'X'}{cross_str} |")
    L(f"| BBI | {_fmt(bbi)} | |")
    L(f"| 距白线/黄线 | {dist_w:.1f}% / {dist_y:.1f}% | |")
    L(f"| 综合评分 | {score}/5 | |")
    L("")

    sig_str = " + ".join(signals) if signals else "无"
    L(f"**B1 信号**: {sig_str}  |  B1/B2/B3: {'✓' if b1 else 'X'}/{'✓' if b2 else 'X'}/{'✓' if b3 else 'X'}")
    suo = "超缩量" if suo_extreme else ("适当缩量" if suo_ok else "否")
    L(f"**缩量**: {suo}  |  单针下20: {'✓' if zhen20 else 'X'}  |  洗盘异动: {'✓' if wash else 'X'}")
    warns = []
    if rev: warns.append("转势(白线走平/向下)")
    if dead: warns.append("死叉")
    if bk: warns.append("破线")
    if warns:
        L(f"**⚠️ 风险**: {', '.join(warns)}")
    L("")


def _section_fundamentals(lines, f):
    L = lines.append
    L("## 基本面")
    L("")
    src = f.get("source", "?")
    L(f"*数据源: {src}*")
    L("")
    L(f"| 指标 | 数值 |")
    L(f"|------|------|")
    L(f"| 营业总收入 | {_fmt_amount(f.get('revenue'))} |")
    L(f"| 归母净利润 | {_fmt_amount(f.get('net_profit'))} |")
    L(f"| ROE | {_fmt_pct(f.get('roe'))} |")
    L(f"| 毛利率 | {_fmt_pct(f.get('gross_margin'))} |")
    L(f"| 净利率 | {_fmt_pct(f.get('net_margin'))} |")
    L(f"| 资产负债率 | {_fmt_pct(f.get('debt_ratio'))} |")
    L(f"| 经营现金流 | {_fmt_amount(f.get('op_cashflow'))} |")
    L(f"| EPS | {_fmt(f.get('eps'))} |")
    L(f"| BVPS | {_fmt(f.get('bvps'))} |")
    L(f"| 营收增速 | {_fmt_pct(f.get('growth_revenue'))} |")
    L(f"| 利润增速 | {_fmt_pct(f.get('growth_profit'))} |")
    L("")
    quality = f.get("quality", {})
    if quality:
        L(f"**质量判断**: 盈利={quality.get('profit_quality','?')} 现金流={quality.get('cashflow_health','?')} 增长={quality.get('growth_visibility','?')}")
        L("")


def _section_valuation(lines, v):
    L = lines.append
    L("## 估值")
    L("")
    L(f"| 指标 | 数值 |")
    L(f"|------|------|")
    L(f"| PE(TTM) | {_fmt(v.get('pe'))} |")
    pe_pct = v.get("pe_pct_5y")
    if pe_pct is not None:
        L(f"| PE 5年分位 | {pe_pct}% |")
    L(f"| PB | {_fmt(v.get('pb'))} |")
    pb_pct = v.get("pb_pct_5y")
    if pb_pct is not None:
        L(f"| PB 5年分位 | {pb_pct}% |")
    L(f"| 总市值 | {_fmt_amount(v.get('total_mv'))} |")
    L(f"| 流通市值 | {_fmt_amount(v.get('circ_mv'))} |")
    L("")


def _section_chip(lines, chip):
    L = lines.append
    L("## 筹码分布")
    L("")
    L(f"| 指标 | 数值 |")
    L(f"|------|------|")
    pr = chip.get("profit_ratio")
    L(f"| 获利比例 | {pr*100:.1f}%" if pr else "| 获利比例 | — |")
    L(f"| 平均成本 | {_fmt(chip.get('avg_cost'))} |")
    c90 = chip.get("concentration_90")
    L(f"| 90%集中度 | {c90*100:.1f}%" if c90 else "| 90%集中度 | — |")
    L(f"| 筹码状态 | {chip.get('chip_status', '?')} |")
    L("")


def _section_fund_flow(lines, ff, ind):
    L = lines.append
    L("## 资金面")
    L("")
    L(f"| 指标 | 数值 |")
    L(f"|------|------|")
    L(f"| 主力净流入 | {_fmt_amount(ff.get('主力净流入'))} |")
    L(f"| 超大单净流入 | {_fmt_amount(ff.get('超大单净流入'))} |")
    L(f"| 涨跌幅 | {_fmt_pct(ind.get('change_pct'))} |")
    L("")


def _section_news(lines, nd):
    L = lines.append
    L("## 近期消息")
    L("")

    news = nd.get("news", [])
    if news:
        L("### 新闻")
        for n in news[:8]:
            L(f"- [{n.get('time','')}] {n.get('title','')}")
        L("")

    reports = nd.get("reports", [])
    if reports:
        L("### 研报")
        for r in reports[:5]:
            L(f"- [{r.get('date','')}] [{r.get('rating','')}] {r.get('title','')} ({r.get('org','')})")
        L("")

    announcements = nd.get("announcements", [])
    if announcements:
        L("### 公告")
        for a in announcements[:8]:
            L(f"- [{a.get('date','')}] {a.get('title','')}")
        L("")


def _section_sector(lines, ctx, code, name, ind):
    L = lines.append
    L("## 板块定位")
    L("")
    if isinstance(ctx, dict):
        L(f"- 板块: {ctx.get('name','?')}  |  排名: {ctx.get('rank','?')}")
        L(f"- B1密度: {ctx.get('b1_density','?')}  |  成分股: {ctx.get('total_stocks','?')}只")
        peers = ctx.get("top_peers", [])
        if peers:
            L("")
            L("### 同板块对比")
            L("| 名称代码 | J值 | 评分 | 趋势 | 信号 |")
            L("|----------|-----|------|------|------|")
            for p in peers[:8]:
                sig = "+".join(p.get("信号", [])) or "—"
                L(f"| {p.get('name','?')}({p.get('code','?')}) | J={p.get('J','?')} | {p.get('评分','?')} | {p.get('趋势','?')} | {sig} |")
            L("")
    elif isinstance(ctx, str):
        L(ctx)
    L("")


def _section_market(lines, mk):
    L = lines.append
    L("## 市场大局")
    L("")
    L("| 指数 | 最新价 | 涨跌幅 |")
    L("|------|--------|--------|")
    for idx_name in ["上证指数", "深证成指", "创业板指", "沪深300"]:
        info = mk.get(idx_name, {})
        L(f"| {idx_name} | {_fmt(info.get('最新价'))} | {_fmt_pct(info.get('涨跌幅'))} |")
    north = mk.get("北向资金", {}).get("净流入")
    if north is not None:
        L(f"\n北向资金净流入: **{_fmt_amount(north)}**")
    top = mk.get("领涨板块", [])
    if top:
        top_str = " | ".join(f"{p['板块名称']}({_fmt_pct(p.get('涨跌幅'))})" for p in top[:5])
        L(f"\n领涨: {top_str}")
    bottom = mk.get("领跌板块", [])
    if bottom:
        bot_str = " | ".join(f"{p['板块名称']}({_fmt_pct(p.get('涨跌幅'))})" for p in bottom[:5])
        L(f"\n领跌: {bot_str}")
    L("")
