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


# ============================================================
# Phase C: 持仓报告 + 日终追踪报告
# ============================================================

def generate_holdings_report(positions: list, daily_data: dict = None) -> str:
    """生成持仓概览 Markdown 报告"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lines.append
    L(f"# 持仓概览报告")
    L(f"> {now}  {len(positions)}只持仓")
    L("")

    L("| 代码 | 名称 | 成本 | 数量 | 现价 | 市值 | 浮动盈亏 | 浮动盈亏% | 策略 | B1状态 |")
    L("|------|------|------|------|------|------|----------|-----------|------|--------|")
    total_mv = 0
    total_pnl = 0
    for p in positions:
        code = p.get("code", "")
        name = p.get("name", "")
        cost = p.get("avg_cost", 0) or 0
        qty = p.get("total_qty", 0) or 0
        strategy = p.get("strategy", "") or ""
        mv = 0
        pnl = 0
        pnl_pct = 0
        close = 0
        b1_status = "—"

        if daily_data and code in daily_data:
            ind = daily_data[code]
            close = ind.get("last", 0) or 0
            mv = round(qty * close, 2)
            pnl = round(qty * (close - cost), 2)
            pnl_pct = round((close - cost) / cost * 100, 2) if cost else 0
            sigs = ind.get("信号", [])
            if sigs:
                b1_status = "+".join(sigs[:2])
            elif ind.get("J", 999) < 20:
                b1_status = "近B1"
            else:
                b1_status = ind.get("趋势", "")

        total_mv += mv
        total_pnl += pnl
        L(f"| {code} | {name[:8]} | {cost:.2f} | {qty} | {close:.2f} | {mv:.0f} | {pnl:+.0f} | {pnl_pct:+.1f}% | {strategy} | {b1_status} |")

    L("")
    L(f"**总市值**: {total_mv:,.0f}  **总浮动盈亏**: {total_pnl:+,.0f}")
    L("")
    return "\n".join(lines)


def generate_daily_review_md(summary: dict) -> str:
    """生成日终追踪 Markdown 日报"""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lines.append
    L(f"# 知行日终追踪报告")
    L(f"> {summary.get('date', '')}  {now}")
    L(f"> 关注票: {summary.get('watchlist_scanned',0)}  持仓快照: {summary.get('positions_snapshotted',0)}")
    L("")

    new_b1 = summary.get("new_b1", [])
    if new_b1:
        L(f"## 新B1信号 ({len(new_b1)}只)")
        L("")
        L("| 代码 | 名称 | J | 评分 | 趋势 | 信号 |")
        L("|------|------|---|------|------|------|")
        for b in new_b1:
            L(f"| {b['code']} | {b.get('name','')[:8]} | {b.get('J','?')} | {b.get('score','?')} | {b.get('trend','')} | {'+'.join(b.get('signals',[])[:2])} |")
        L("")

    b1_lost = summary.get("b1_lost", [])
    if b1_lost:
        L(f"## B1消失 ({len(b1_lost)}只) → 进入观察期")
        L("")
        for b in b1_lost:
            L(f"- {b['code']} {b.get('name','')}: J={b.get('J','?')} ({b.get('from_stage','')}→observing)")
        L("")

    near_b1 = summary.get("near_b1", [])
    if near_b1:
        L(f"## 近B1观察区 ({len(near_b1)}只, J<20)")
        L("")
        for b in near_b1:
            L(f"- {b['code']} {b.get('name','')}: J={b.get('J','?')} 评分={b.get('score','?')}")
        L("")

    stage_changes = summary.get("stage_changes", [])
    if stage_changes:
        L(f"## 状态变更 ({len(stage_changes)}条)")
        L("")
        L("| 代码 | 原状态 | 新状态 |")
        L("|------|--------|--------|")
        for c in stage_changes:
            L(f"| {c.get('code','')} | {c.get('from','')} | {c.get('to','')} |")
        L("")

    expired = summary.get("expired_cleaned", [])
    if expired:
        L(f"## 过期清理 ({len(expired)}只, 7天观察期满)")
        L("")
        for code in expired:
            L(f"- {code} → archived")
        L("")

    alerts = summary.get("alerts", [])
    if alerts:
        L(f"## 预警 ({len(alerts)}条)")
        L("")
        for a in alerts:
            L(f"- [{a.get('type','')}] {a.get('code','')} {a.get('name','')}: {a.get('detail','')}")
            if a.get("changes"):
                L(f"  - 变化: {', '.join(a['changes'])}")
        L("")

    errors = summary.get("errors", [])
    if errors:
        L(f"## 错误 ({len(errors)}条)")
        L("")
        for e in errors:
            L(f"- {e}")
        L("")

    L("---")
    L(f"*知行系统 {now}  仅供参考，不构成投资建议*")
    return "\n".join(lines)

