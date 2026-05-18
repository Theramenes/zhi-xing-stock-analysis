"""
报告生成器 — 严格对齐 templates/板块扫描.md 输出模板
"""
import json, os
from datetime import datetime


def _fmt_pct(v): return f"{v:+.2f}%" if v else "—"
def _fmt_flow(v):
    if abs(v) >= 1: return f"{v:+.2f}亿"
    if abs(v) >= 0.01: return f"{v*10000:+.0f}万"
    return "—"


def generate_overview_report(result) -> str:
    """纯板块概览（用户未提B1/交易机会）"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []; L = lines.append
    L(f"# {result.sector_name}行业分析")
    L(f"> {now}  iFind  {result.total_stocks}只  {len(result.groups)}细分行业")
    L("")
    _section1_overview(lines, result)
    return "\n".join(lines)


def generate_b1_report(combined: dict) -> str:
    """
    板块B1扫描报告 — 对齐模板: 1.行业分析 2.个股分析(细分行业) 3.板块重点
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    ov = combined.get("overview"); b1 = combined.get("b1"); banned = combined.get("banned", [])
    name = ov.sector_name if ov else (b1.name if b1 else "")
    lines = []; L = lines.append

    L(f"# {name}板块B1扫描")
    ban_info = ""
    if banned:
        ban_types = sorted(set(c[:3] for c in banned))
        ban_info = f"  已排除{', '.join(ban_types)}xx共{len(banned)}只"
    L(f"> {now}  iFind  {ov.total_stocks if ov else '?'}只成分股{ban_info}")
    if b1:
        L(f"> B1:{len(b1.b1_stocks)}  近B1:{len(b1.near_b1_stocks)}  趋势持有:{len(b1.trend_hold_stocks)}  缩爆:{len(b1.suo_bao_candidates)}  {b1.elapsed:.0f}s")
    L("")

    # ==== Section 1: 行业板块分析 ====
    if ov:
        _section1_overview(lines, ov)

    # ==== Section 2: 板块个股分析 ====
    if not b1 or not b1.stocks:
        L("## 2. 板块个股分析")
        L("")
        L("*无B1扫描数据*")
        L("")
    else:
        _section2_stocks(lines, b1, ov)

    # ==== Section 3: 板块重点 ====
    L("## 3. 板块重点")
    L("")
    if b1 and b1.b1_stocks:
        L("| 名称代码 | 主营业务 | 推荐理由 |")
        L("| --- | ------ | ----- |")
        for s in b1.b1_stocks[:10]:
            biz = _get_biz(s.code, ov, max_len=60)
            multi = len(s.信号)
            理由 = f"{'+'.join(s.信号[:2])}"
            if multi >= 3: 理由 += " 三重共振"
            if s.超缩量: 理由 += " 超缩"
            if s.评分 >= 3: 理由 += f" 高评分{s.评分}"
            L(f"| {s.name}({s.code}) | {biz} | {理由} |")
        L("")

    if b1 and b1.near_b1_stocks:
        L(f"**近B1观察区**: {', '.join(f'{s.name}({s.code})' for s in b1.near_b1_stocks[:8])}")
        L("")

    if banned:
        L(f"*已排除: {len(banned)}只（{', '.join(banned[:5])}{'...' if len(banned)>5 else ''}）*")
    L("---")
    L(f"*知行系统 {now}  仅供参考*")
    return "\n".join(lines)


def _section1_overview(lines, ov):
    """板块分析 section（概览和B1报告共享）"""
    L = lines.append
    L("## 1. 行业板块分析")
    L("")

    # 行业结构
    if ov.industry_tree:
        from scanning.industry_analyzer import IndustryAnalyzer
        analyzer = IndustryAnalyzer()
        tree = analyzer.describe_tree(ov.industry_tree)
        L("### 行业板块逻辑梳理")
        L("")
        L("```")
        L(tree)
        L("```")
        L("*关联分析由AI推理完成*")
        L("")

    # 板块概述
    L("### 板块概述")
    L("")
    if ov.groups:
        L("| 行业/细分行业 | 股票数 | 近5日涨跌 | 近5日资金 | 涨/跌 | 涨停/跌停 |")
        L("| ---- | --- | -------- | -------- | --- | --- |")
        for gname, g in ov.groups.items():
            if not g.stocks: continue
            short = gname.split('-')[-1] if '-' in gname else gname
            L(f"| {short} | {len(g.stocks)} | {_fmt_pct(g.avg_change_5d)} | {_fmt_flow(g.total_fund_flow)} | {g.up_count}/{g.down_count} | {g.limit_up_count}/{g.limit_down_count} |")
        L("")

    # 核心与异动
    L("### 核心与异动标的")
    L("")
    L("| 名称代码 | 主营业务 | 核心重要度原因 |")
    L("| ---- | ------ | ----- |")
    seen = set()
    for gname, g in ov.groups.items():
        for s in g.anomaly_stocks[:3]:
            if s.code in seen: continue
            seen.add(s.code)
            reason = []
            if s.leader_tag: reason.append(f"龙头:{s.leader_tag[:12]}")
            if abs(s.change_pct) >= 5: reason.append(f"{'涨' if s.change_pct>0 else '跌'}{abs(s.change_pct):.0f}%")
            if s.volume_ratio >= 3: reason.append(f"量比{s.volume_ratio:.0f}x")
            if abs(s.fund_flow) >= 5e8: reason.append(f"资金{_fmt_flow(s.fund_flow/1e8)}")
            L(f"| {s.name}({s.code}) | {_get_biz(s.code, ov, max_len=60)} | {'; '.join(reason) if reason else '异动'} |")
        if len(seen) >= 10: break
    L("")

    # 涨跌停
    total_up = sum(g.limit_up_count for g in ov.groups.values())
    total_down = sum(g.limit_down_count for g in ov.groups.values())
    L(f"**涨停: {total_up}  跌停: {total_down}**")
    L("")


def _section2_stocks(lines, b1, ov):
    """板块个股分析 section"""
    L = lines.append
    L("## 2. 板块个股分析")
    L("")

    # 按细分行业分组
    by_ind = {}
    for s in b1.stocks:
        ind = _get_industry(s.code, ov)
        key = ind.split('-')[-1] if ind and '-' in ind else (ind or '其他')
        if key not in by_ind: by_ind[key] = []
        by_ind[key].append(s)

    if len(b1.stocks) > 50:
        # 按细分行业拆分表
        for ind_name in sorted(by_ind.keys()):
            gs = by_ind[ind_name]
            L(f"### {ind_name}（{len(gs)}只）")
            L("")
            _stock_table(L, gs, ov)
            L("")
    else:
        L("### 细分行业个股")
        L("")
        all_sorted = (
            sorted(b1.b1_stocks, key=lambda x: len(x.信号), reverse=True)
            + sorted(b1.near_b1_stocks, key=lambda x: x.J)
            + sorted(b1.trend_hold_stocks, key=lambda x: x.评分, reverse=True)
        )
        _stock_table(L, all_sorted, ov)
        L("")


def _stock_table(L, stocks, ov):
    """个股表格 — 严格对齐模板字段"""
    L("| 名称代码 | 主营业务 | 细分行业 | 现价 | 涨跌幅 | 换手率 | 量比 | 成交量 | B1状态 |")
    L("| ---- | ------ | ------- | ---- | ----- | ------ | --- | ------ | ----- |")
    for s in stocks[:60]:
        biz = _get_biz(s.code, ov)[:12]
        ind = _get_industry(s.code, ov)
        ind_short = ind.split('-')[-1] if ind and '-' in ind else (ind or '')
        chg, turnover, vol_ratio = _get_market(s.code, ov)
        sig = '+'.join(s.信号[:2]) if s.信号 else ('B1' if s.基础B1 else ('B2' if s.基础B2 else ('近B1' if s.J < 20 else '—')))
        vol_str = f"{s.成交量:.0f}手" if hasattr(s, '成交量') else "—"
        L(f"| {s.name}({s.code}) | {biz} | {ind_short} | {s.last:.2f} | {_fmt_pct(chg)} | {turnover:.1f}% | {vol_ratio:.1f} | {vol_str} | {sig} |")


def _get_biz(code, ov, max_len=30):
    """从 overview stocks 取主营业务，fallback 到三级行业名。转义 | 防表格错位"""
    if ov:
        for s in ov.stocks:
            if s.code == code:
                raw = ''
                if hasattr(s, 'biz') and s.biz and s.biz != s.industry_path.split('-')[-1]:
                    raw = s.biz[:max_len]
                else:
                    parts = s.industry_path.split('-')
                    raw = parts[-1] if parts else ''
                return raw.replace('|', '/')
    return ""


def _get_industry(code, ov):
    if ov:
        for s in ov.stocks:
            if s.code == code:
                return s.industry_path
    return ""


def _get_market(code, ov):
    """获取涨跌幅/换手率/量比"""
    if ov:
        for s in ov.stocks:
            if s.code == code:
                return s.change_pct, s.turnover, s.volume_ratio
    return 0, 0, 0


def save_report(content, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return os.path.abspath(path)


def save_raw_data(data, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2, default=str)
    return os.path.abspath(path)
