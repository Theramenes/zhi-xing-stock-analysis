"""
知行股票分析系统 — 统一 CLI 入口
用法:
  python cli.py indicator --symbol 603206 [--input candles.json]
  python cli.py suo-bao --symbol 603206 [--input candles.json]
  python cli.py scan-sector --name 锂电池 [--output report.md] [--publish]
  python cli.py scan-market [--output report.md]
  python cli.py report --input result.json --output report.md
  python cli.py publish --input report.md [--title TITLE] [--folder TOKEN]
"""
import argparse
import json
import sys
import os
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from indicators.b1_calculator import compute_single
from indicators.suo_bao_b1 import scan as suo_bao_scan


def _now_short():
    from datetime import date
    return date.today().strftime("%Y-%m-%d")


def cmd_indicator(args):
    """计算单只股票的知行指标"""
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
    else:
        print(json.dumps({"error": "请提供K线JSON数据（stdin 或 --input 文件）"}, ensure_ascii=False))
        return

    code = args.symbol or data.get("symbol", "").split(".")[0]
    candles = data.get("candles", [])
    if not candles:
        inner = data.get("data", {})
        candles = inner.get("candles", [])
        code = code or inner.get("symbol", "").split(".")[0]
    if not candles:
        print(json.dumps({"error": "未找到K线数据"}, ensure_ascii=False))
        return

    result = compute_single(code, candles)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_suo_bao(args):
    """扫描单只股票的缩爆B1模式"""
    if args.input:
        with open(args.input, 'r', encoding='utf-8') as f:
            data = json.load(f)
    elif not sys.stdin.isatty():
        data = json.load(sys.stdin)
    else:
        print(json.dumps({"error": "请提供K线JSON数据"}, ensure_ascii=False))
        return

    code = args.symbol or data.get("symbol", "").split(".")[0]
    name = data.get("name", code)
    candles = data.get("candles", [])
    if not candles:
        inner = data.get("data", {})
        candles = inner.get("candles", [])
    if not candles:
        print(json.dumps({"error": "未找到K线数据"}, ensure_ascii=False))
        return

    result = suo_bao_scan(code, name, candles, D=args.D, S=args.S, V=args.V, N=args.N)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_scan_overview(args):
    """板块概览：不扫个股，只看板块级别数据（走势/资金/龙头/异动）"""
    from scanning.sector_scanner import SectorOverview
    from reporting.generator import generate_overview_report, save_report

    query = args.name
    if not query:
        print(json.dumps({"error": "请指定板块（--name 电池）"}, ensure_ascii=False))
        return

    scanner = SectorOverview()
    name, stype = scanner.resolve(query)
    print(f"查询: {query} → {name} ({'行业' if stype == 'industry' else '概念'})")

    result = scanner.scan(query)
    if not result or result.total_stocks == 0:
        print("无数据")
        return

    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "reports", "local_markdown")
    os.makedirs(data_dir, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    md = generate_overview_report(result)
    output = args.output or os.path.join(data_dir, f"{result.sector_name}概览_{ts}.md")
    path = save_report(md, output)
    print(f"\n报告: {path}")
    print(f"股票: {result.total_stocks}  细分行业: {len(result.groups)}  耗时: {result.elapsed:.0f}s")

    # 默认发飞书
    if args.publish:
        from reporting.feishu_publisher import publish_report, notify_scan_complete
        url = publish_report(path, title=f"{result.sector_name}板块概览")
        if url:
            print(f"飞书: {url}")
            notify_scan_complete(result.sector_name, 0, 0, url)


def cmd_scan_b1(args):
    """板块B1扫描：概览 + 黑名单过滤 + 逐只K线 + 知行指标 + 按细分行业输出"""
    from scanning.sector_scanner import SectorB1Scanner
    from reporting.generator import generate_b1_report, save_report, save_raw_data

    query = args.name
    if not query:
        print(json.dumps({"error": "请指定板块（--name 电池）"}, ensure_ascii=False))
        return

    scanner = SectorB1Scanner(workers=args.workers, use_cache=not args.no_cache)
    combined = scanner.scan(query, days=args.days)

    b1 = combined.get("b1")
    ov = combined.get("overview")
    if not b1 and not ov:
        print("无结果")
        return

    today_str = datetime.now().strftime("%Y-%m-%d")
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "reports", "local_markdown")
    track_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                             "data", today_str)
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(track_dir, exist_ok=True)

    name = ov.sector_name if ov else query
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    md = generate_b1_report(combined)
    output = args.output or os.path.join(data_dir, f"{name}B1扫描_{ts}.md")
    path = save_report(md, output)

    if b1:
        # B1候选追踪文件
        candidates = [s.code for s in b1.b1_stocks] + [s.code for s in b1.near_b1_stocks]
        save_raw_data(
            {"date": today_str, "sector": name, "candidates": candidates,
             "b1": [s.code for s in b1.b1_stocks], "near_b1": [s.code for s in b1.near_b1_stocks]},
            os.path.join(track_dir, f"B1_candidate_{name}.json")
        )
    print(f"\n报告: {path}")
    if b1:
        print(f"B1:{len(b1.b1_stocks)} 近B1:{len(b1.near_b1_stocks)} 趋势:{len(b1.trend_hold_stocks)}")
    if combined.get("banned"):
        print(f"已排除: {len(combined['banned'])}只 ({', '.join(combined['banned'][:8])})")

    # 自动入库: 将B1/近B1票写入 watchlist + b1_candidate
    if b1 and not args.no_auto_save:
        from storage.portfolio_db import (add_to_watchlist, record_b1_scan, add_b1_candidate, record_watchlist_daily)
        scan_id = record_b1_scan("sector", name, total=len(b1.stocks),
                                 b1=len(b1.b1_stocks), near=len(b1.near_b1_stocks),
                                 report_path=path, elapsed=b1.elapsed)
        auto_saved = 0
        for s in (b1.b1_stocks or []):
            d = s.to_dict() if hasattr(s, "to_dict") else s.__dict__
            add_to_watchlist(d["code"], d.get("name", ""), source="auto_scan",
                             reason=f"{name} B1", tags=[name])
            add_b1_candidate(scan_id, d["code"], d.get("name", ""), name, "B1", d)
            record_watchlist_daily(d["code"], d)
            auto_saved += 1
        for s in (b1.near_b1_stocks or []):
            d = s.to_dict() if hasattr(s, "to_dict") else s.__dict__
            add_to_watchlist(d["code"], d.get("name", ""), source="auto_scan",
                             reason=f"{name} 近B1", tags=[name])
            add_b1_candidate(scan_id, d["code"], d.get("name", ""), name, "near_B1", d)
            record_watchlist_daily(d["code"], d)
            auto_saved += 1
        print(f"自动入库: {auto_saved}只 B1候选+关注列表")

    # 默认发飞书
    if args.publish:
        from reporting.feishu_publisher import publish_report, notify_scan_complete
        url = publish_report(path, title=f"{name}B1扫描")
        if url:
            print(f"飞书: {url}")
            if b1:
                notify_scan_complete(name, len(b1.b1_stocks), len(b1.near_b1_stocks), url)


def cmd_scan_market(args):
    """全市场扫描（以板块为单元循环）"""
    from scanning.sector_scanner import SectorScanner
    from reporting.generator import generate_sector_report, save_report, save_raw_data
    from data_source.registry import registry as ds_registry

    # 获取全行业板块列表
    ifind = ds_registry.get_source("ifind")
    sectors = []
    if ifind and ifind.is_available():
        sectors = ifind.get_sector_list("industry")
    if not sectors:
        free = ds_registry.get_source("free")
        if free and free.is_available():
            sectors = free.get_sector_list("industry")
    if not sectors:
        print(json.dumps({"error": "无法获取行业板块列表"}, ensure_ascii=False))
        return

    print(f"全市场扫描: {len(sectors)} 个行业板块")

    scanner = SectorScanner(workers=args.workers, use_cache=not args.no_cache)
    all_b1 = []
    all_near = []
    sector_summaries = []

    for i, sector in enumerate(sectors[:args.max_sectors or len(sectors)]):
        print(f"\n{'='*50}")
        print(f"[{i+1}/{min(len(sectors), args.max_sectors or len(sectors))}] {sector.name}")
        result = scanner.scan(sector.name, days=args.days)
        all_b1.extend(result.b1_stocks)
        all_near.extend(result.near_b1_stocks)
        sector_summaries.append({
            "name": sector.name,
            "members": len(result.members),
            "b1": len(result.b1_stocks),
            "near_b1": len(result.near_b1_stocks),
            "trend_hold": len(result.trend_hold_stocks),
            "errors": len(result.errors),
        })

    # 生成汇总报告
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                            "data", "reports")
    os.makedirs(data_dir, exist_ok=True)

    lines = []
    lines.append("# 全市场B1信号扫描报告")
    lines.append(f"> 扫描板块: {len(sector_summaries)} 个  |  B1信号合计: {len(all_b1)}")
    lines.append("")
    lines.append("## 行业B1密度排行")
    lines.append("")
    lines.append("| 板块 | 成分股 | B1 | 近B1 | 趋势持有 | 错误 |")
    lines.append("|:---|---:|:---:|:---:|:---:|:---:|")
    for ss in sorted(sector_summaries, key=lambda x: x["b1"] + x["near_b1"] * 0.5, reverse=True):
        if ss["b1"] + ss["near_b1"] == 0:
            continue
        lines.append(f"| {ss['name']} | {ss['members']} | {ss['b1']} | {ss['near_b1']} | {ss['trend_hold']} | {ss['errors']} |")
    lines.append("")

    output = args.output or os.path.join(data_dir, "全市场B1扫描报告.md")
    md_content = "\n".join(lines)
    report_path = save_report(md_content, output)
    print(f"\n汇总报告: {report_path}")


def cmd_report(args):
    """从原始数据JSON生成报告"""
    from reporting.generator import generate_sector_report, save_report
    from scanning.sector_scanner import SectorScanResult, StockScanResult

    with open(args.input, 'r', encoding='utf-8') as f:
        data = json.load(f)

    # 从原始JSON重建结果对象
    result = SectorScanResult(name=data.get("name", ""))
    for sd in data.get("stocks", []):
        s = StockScanResult()
        for k, v in sd.items():
            if hasattr(s, k):
                setattr(s, k, v)
        result.stocks.append(s)

    # 重新分类
    result.b1_stocks = [s for s in result.stocks if s.信号 or s.基础B1 or s.基础B2]
    result.near_b1_stocks = [s for s in result.stocks if not s.信号 and not s.基础B1 and s.J < 20]
    result.trend_hold_stocks = [s for s in result.stocks if s not in result.b1_stocks and s not in result.near_b1_stocks and s.评分 >= 3 and s.趋势 == "多头"]
    result.suo_bao_candidates = [s for s in result.stocks if s.suo_bao and s.suo_bao.get("is_active")]

    md = generate_sector_report(result)
    output = args.output or args.input.replace(".json", ".md")
    path = save_report(md, output)
    print(f"报告: {path}")


def cmd_publish(args):
    """发布本地MD报告到飞书"""
    from reporting.feishu_publisher import publish_report

    url = publish_report(args.input, title=args.title, folder_token=args.folder)
    if url:
        print(f"飞书文档: {url}")
    else:
        print("发布失败")


# ============================================================
# Phase C: 持仓 / 关注 / B1追踪 CLI
# ============================================================

def cmd_holdings_add(args):
    """新增或更新持仓头寸"""
    from storage.portfolio_db import add_position
    result = add_position(args.code, args.name or args.code, args.cost, args.qty,
                          strategy=args.strategy or "", notes=args.notes or "",
                          stop_loss=args.stop_loss, target_price=args.target)
    print(f"{'更新' if result == 2 else '新增'}持仓: {args.code} {args.name or ''} 成本={args.cost} 数量={args.qty}")


def cmd_holdings_list(args):
    """列出当前持仓"""
    from storage.portfolio_db import list_positions, get_pnl_summary
    positions = list_positions()
    pnl = get_pnl_summary(30)
    print(f"=== 持仓列表 ({len(positions)}只) === 近30日: 已实现盈亏 {pnl['total_pnl']} | 平均 {pnl['avg_pnl_pct']}%")
    print(f"{'代码':<8} {'名称':<10} {'成本':>8} {'数量':>8} {'市值' if False else ''} {'策略':<6}")
    for p in positions:
        print(f"{p['code']:<8} {p.get('name','')[:8]:<10} {p.get('avg_cost',0):>8.2f} {p.get('total_qty',0):>8} {p.get('strategy',''):<6}")
        if args.verbose:
            print(f"    首次买入:{p.get('first_buy_date','')} 最后交易:{p.get('last_trade_date','')} 备注:{p.get('notes','')}")


def cmd_transaction_add(args):
    """新增交易记录"""
    from storage.portfolio_db import add_transaction
    tx_id = add_transaction(args.code, args.date, args.direction, args.qty, args.price,
                            reason=args.reason or "", memo=args.memo or "")
    if tx_id:
        print(f"交易记录 #{tx_id}: {args.direction} {args.code} {args.qty}股 @{args.price}")
    else:
        print("交易记录失败")


def cmd_transaction_list(args):
    """查看交易流水"""
    from storage.portfolio_db import list_transactions
    txs = list_transactions(args.code, days=args.days, limit=args.limit)
    print(f"=== 交易流水 ({len(txs)}条) ===")
    for t in txs:
        pnl_str = f" 盈亏={t.get('pnl',''):.2f}" if t.get('pnl') else ""
        print(f"{t['trade_date']} {t['direction']:>8} {t['code']:<8} {t.get('name',''):<8} {t['qty']:>6}股 @{t['price']:.2f}{pnl_str}  {t.get('reason','')}")


def cmd_watchlist_add(args):
    """加入关注列表"""
    from storage.portfolio_db import add_to_watchlist
    import json
    tags = json.loads(args.tags) if args.tags else None
    result = add_to_watchlist(args.code, args.name or args.code, source="manual",
                              reason=args.reason or "", priority=args.priority, tags=tags,
                              added_price=args.price, notes=args.notes or "")
    print(f"{'更新' if result == 2 else '新增'}关注: {args.code} {args.name or ''} [优先级={args.priority}]")


def cmd_watchlist_list(args):
    """查看关注列表"""
    from storage.portfolio_db import list_watchlist
    items = list_watchlist(args.status or "active")
    print(f"=== 关注列表 ({len(items)}只) === [{args.status or 'active'}]")
    for w in items:
        tags = w.get("tags", "")
        print(f"  {w['code']:<8} {w.get('name','')[:10]:<10} P={w.get('priority',0)} [{w.get('source','')}] {w.get('reason','')[:30]} {tags}")


def cmd_watchlist_remove(args):
    """移出关注列表"""
    from storage.portfolio_db import remove_from_watchlist
    remove_from_watchlist(args.code, args.reason or "手动移出")
    print(f"已移出关注: {args.code}")


def cmd_daily_review(args):
    """日终追踪流程"""
    from tracking.daily_review import run_daily_review, generate_summary_text
    sectors = None
    if args.sector:
        sectors = [(s.strip(), "industry") for s in args.sector.split(",") if s.strip()]
    summary = run_daily_review(sectors_to_scan=sectors, workers=args.workers)
    text = generate_summary_text(summary)
    print(text)

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            import json
            f.write(json.dumps(summary, ensure_ascii=False, indent=2))
        print(f"\nJSON摘要: {args.output}")


def cmd_b1_tracking(args):
    """查看B1状态追踪历史"""
    from storage.portfolio_db import get_b1_tracking
    tracking = get_b1_tracking(args.code, limit=args.limit)
    if not tracking:
        print(f"无追踪记录: {args.code}")
        return
    print(f"=== B1追踪: {args.code} ({len(tracking)}条) ===")
    for t in tracking:
        print(f"  {t['date']} stage={t['stage']:<16} J={t.get('J','?'):>6} "
              f"trend={t.get('trend',''):<4} score={t.get('score','?')} "
              f"days={t.get('stage_days',0)} {t.get('memo','')}")


def cmd_focus_sector_add(args):
    """添加重点板块"""
    from storage.portfolio_db import add_focus_sector
    import json
    tags = json.loads(args.tags) if args.tags else None
    result = add_focus_sector(args.name, sector_type=args.type or "industry",
                              source=args.source or "manual", priority=args.priority,
                              notes=args.notes or "", tags=tags)
    print(f"{'更新' if result == 2 else '新增'}重点板块: {args.name}")


def cmd_focus_sector_list(args):
    """查看重点板块"""
    from storage.portfolio_db import list_focus_sectors
    sectors = list_focus_sectors(args.status or "active")
    print(f"=== 重点板块 ({len(sectors)}个) ===")
    for s in sectors:
        print(f"  {s['name']:<20} type={s.get('sector_type','')} P={s.get('priority',0)} "
              f"B1密度={s.get('b1_density','?')} 状态={s.get('status','')}")


# ============================================================
# Phase F: LLM 报告解析
# ============================================================

def cmd_llm_stock(args):
    """个股AI技术解读（可选 --sector 触发三层深度分析）"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，跳过 AI 解读。请设置 ZX_LLM_API_KEY 环境变量。")
        return

    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from llm.enhancer import enhance_stock_report, enhance_stock_deep
    from llm.market_context import build_sector_context

    print(f"[LLM Stock] 拉取 {args.symbol} K线...")
    candles = ensure_candles(args.symbol, required_days=args.days)
    if len(candles) < 30:
        print(f"K线不足（{len(candles)}天），无法分析")
        return

    print(f"[LLM Stock] 计算指标...")
    result = compute_single(args.symbol, candles)
    if "error" in result:
        print(f"指标计算失败: {result['error']}")
        return

    name = result.get("name", args.symbol)

    if args.sector:
        # 深度分析：三层（个股 + 板块定位 + 大局研判）
        print(f"[LLM Stock] 拉取板块 '{args.sector}' 上下文 + 横向对比...")
        sector_ctx = build_sector_context(args.sector, args.symbol)
        if sector_ctx:
            print(f"  板块排名: {sector_ctx.get('rank','?')}")
            print(f"  同行对比: {len(sector_ctx.get('top_peers',[]))} 只可对比")
            print(f"  市场环境: {sector_ctx.get('market_context',{}).get('top_sectors','?')}")
        else:
            print(f"  板块数据获取失败，仅做个股分析")
        print(f"[LLM Stock] AI 深度分析中（三层逻辑）...")
        md = enhance_stock_deep(args.symbol, name, result, sector_ctx)
    else:
        print(f"[LLM Stock] AI 解读中...")
        md = enhance_stock_report(args.symbol, name, result)

    if md:
        print(md)
    else:
        print("LLM 调用失败，请检查 API Key 和网络连接。")


def cmd_llm_sector(args):
    """板块扫描 + AI叙事增强"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，跳过 AI 解读。请设置 ZX_LLM_API_KEY 环境变量。")

    from scanning.sector_scanner import SectorB1Scanner
    from llm.enhancer import enhance_sector_report

    scanner = SectorB1Scanner(workers=args.workers)
    combined = scanner.scan(args.name, days=args.days)
    b1 = combined.get("b1")
    if not b1 or not b1.stocks:
        print("扫描无结果")
        return

    if config.available:
        print("[LLM Sector] AI 叙事分析中...")
        md = enhance_sector_report(args.name, {
            "stocks": [s.to_dict() if hasattr(s, 'to_dict') else s for s in b1.stocks],
            "b1_stocks": [s.to_dict() if hasattr(s, 'to_dict') else s for s in b1.b1_stocks],
            "near_b1_stocks": [s.to_dict() if hasattr(s, 'to_dict') else s for s in b1.near_b1_stocks],
        })
        if md:
            print(md)


def cmd_holdings_letter(args):
    """持仓日报"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，请设置 ZX_LLM_API_KEY 环境变量。")
        return

    from storage.db import get_db
    from datetime import datetime, timedelta
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from llm.enhancer import generate_holdings_letter

    db = get_db()
    rows = db.conn.execute(
        "SELECT code, name, total_qty, avg_cost FROM position WHERE total_qty > 0"
    ).fetchall()

    if not rows:
        print("暂无持仓")
        return

    holdings_data = []
    print(f"[Holdings Letter] 拉取 {len(rows)} 只持仓 K线...")
    for code, name, qty, cost in rows:
        candles = ensure_candles(code, required_days=114)
        if len(candles) < 30:
            print(f"  {code} {name}: K线不足，跳过")
            continue
        ind = compute_single(code, candles)
        holdings_data.append({
            "code": code, "name": name, "qty": qty, "cost": cost,
            "last": ind.get("last", 0), "change_pct": ind.get("change_pct", 0),
            "J": ind.get("J"), "RSI": ind.get("RSI"), "趋势": ind.get("趋势"),
            "评分": ind.get("评分"), "信号": ind.get("信号", []),
            "B1_active": bool(ind.get("信号") or ind.get("基础B1")),
            "near_B1": ind.get("J", 999) < 20,
            "超缩量": ind.get("超缩量", False),
            "status_change": "",
        })
        print(f"  {code} {name}: J={ind.get('J')} 评分={ind.get('评分')}")

    if not holdings_data:
        print("无有效持仓数据")
        return

    print("[Holdings Letter] AI 生成中...")
    md = generate_holdings_letter(holdings_data)
    if md:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"已保存到 {args.output}")
        else:
            print(md)
    else:
        print("LLM 调用失败。")


def cmd_holdings_review(args):
    """持仓复盘/监控（LLM分析今日操作得失或当前持仓状态）"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，请设置 ZX_LLM_API_KEY 环境变量。")
        return

    from storage.db import get_db
    from datetime import datetime
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from llm.enhancer import generate_holdings_review
    from storage.portfolio_db import (
        list_positions, list_positions_with_archive,
        get_daily_position_changes, list_transactions
    )

    date = args.date or datetime.now().strftime("%Y-%m-%d")
    today = datetime.now().strftime("%Y-%m-%d")

    mode = args.mode
    if mode == "auto":
        mode = "review" if date == today else "monitor"

    active_positions = list_positions()

    closed_positions = []
    changes = []
    transactions = []
    if mode == "review":
        archived = list_positions_with_archive(date=date, include_active=False)
        closed_positions = archived
        changes = get_daily_position_changes(date=date)
        transactions = [t for t in list_transactions(days=1)
                        if t.get("trade_date") == date]

    def _enrich(pos_list, is_closed=False):
        result = []
        for p in pos_list:
            code = p.get("code")
            name = p.get("name", code)
            try:
                candles = ensure_candles(code, required_days=114)
                if len(candles) < 5:
                    print(f"  {code} {name}: K线不足，跳过")
                    continue
                ind = compute_single(code, candles)
                item = {
                    "code": code,
                    "name": name,
                    "last": ind.get("last", 0),
                    "change_pct": ind.get("change_pct", 0),
                }
                if is_closed:
                    item["archived_qty"] = p.get("total_qty", 0)
                    item["avg_cost"] = p.get("avg_cost", 0)
                    item["closed_price"] = p.get("closed_price", 0)
                    item["realized_pnl"] = p.get("realized_pnl", 0)
                    item["realized_pnl_pct"] = p.get("realized_pnl_pct", 0)
                else:
                    item["qty"] = p.get("total_qty", 0)
                    item["cost"] = p.get("avg_cost", 0)
                    item["J"] = ind.get("J")
                    item["RSI"] = ind.get("RSI")
                    item["趋势"] = ind.get("趋势")
                    item["评分"] = ind.get("评分")
                    item["B1_active"] = bool(ind.get("信号") or ind.get("基础B1"))
                    item["near_B1"] = ind.get("J", 999) < 20
                    item["超缩量"] = ind.get("超缩量", False)
                result.append(item)
                print(f"  {code} {name}: 现价={ind.get('last')} 涨跌={ind.get('change_pct', 0):+.2f}%")
            except Exception as e:
                print(f"  {code} {name}: 行情获取失败 ({e})")
        return result

    print(f"[Holdings Review] mode={mode} date={date}")
    print(f"[Holdings Review] 拉取 {len(active_positions)} 只当前持仓行情...")
    active_data = _enrich(active_positions, is_closed=False)

    closed_data = []
    if mode == "review" and closed_positions:
        print(f"[Holdings Review] 拉取 {len(closed_positions)} 只已清仓行情...")
        closed_data = _enrich(closed_positions, is_closed=True)

    for c in changes:
        if not c.get("name"):
            for p in active_positions + closed_positions:
                if p.get("code") == c["code"]:
                    c["name"] = p.get("name", c["code"])
                    break

    raw_data = {
        "mode": mode,
        "date": date,
        "active": active_data,
        "closed": closed_data,
        "changes": changes,
        "transactions": transactions,
    }

    print("[Holdings Review] AI 生成中...")
    md = generate_holdings_review(raw_data)
    if md:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"已保存到 {args.output}")
        else:
            print(md)
    else:
        print("LLM 调用失败。")


def cmd_watchlist_report(args):
    """关注列表监控报告"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，请设置 ZX_LLM_API_KEY 环境变量。")
        return

    from storage.db import get_db
    from datetime import datetime, timedelta
    from llm.enhancer import generate_watchlist_report

    db = get_db()
    today = datetime.now().strftime("%Y-%m-%d")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

    # 获取今日活跃关注列表
    active = db.conn.execute(
        "SELECT code, name FROM watchlist WHERE status='active'"
    ).fetchall()

    if not active:
        print("暂无活跃关注")
        return

    active_list = []
    for code, name in active:
        row = db.conn.execute(
            "SELECT close, change_pct, J, 趋势, 评分, B1_active, near_B1, signals "
            "FROM watchlist_daily WHERE code=? AND date=? ORDER BY date DESC LIMIT 1",
            (code, today)
        ).fetchone()
        if row:
            sigs = json.loads(row[7]) if row[7] else []
            active_list.append({
                "code": code, "name": name,
                "close": row[0], "change_pct": row[1] or 0,
                "J": row[2], "趋势": row[3], "评分": row[4],
                "B1_active": bool(row[5]), "near_B1": bool(row[6]),
                "信号": sigs,
            })

    # 获取今日变化
    changes_rows = db.conn.execute(
        "SELECT code, name, status_change FROM watchlist_daily "
        "WHERE date=? AND status_change IS NOT NULL AND status_change != ''",
        (today,)
    ).fetchall()

    changes = []
    new_b1 = []
    b1_lost = []
    for code, name, sc_change in changes_rows:
        if sc_change:
            try:
                change_data = json.loads(sc_change) if isinstance(sc_change, str) else sc_change
                change_data["code"] = code
                change_data["name"] = name
                changes.append(change_data)
            except Exception:
                changes.append({"code": code, "name": name, "change": str(sc_change)})

    watchlist_data = {
        "date": today,
        "active": active_list,
        "changes": changes,
        "new_B1": new_b1,
        "b1_lost": b1_lost,
        "near_b1_new": [],
    }

    print(f"[Watchlist Report] 活跃关注: {len(active_list)} 只，变化: {len(changes)} 项")
    print("[Watchlist Report] AI 生成中...")
    md = generate_watchlist_report(watchlist_data)
    if md:
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"已保存到 {args.output}")
        else:
            print(md)
    else:
        print("LLM 调用失败。")


def cmd_account_update(args):
    """更新账户快照"""
    from storage.portfolio_db import save_account_snapshot
    stock_value = args.total - args.cash
    ratio = args.position_ratio or (stock_value / args.total * 100)
    pnl = args.pnl or 0
    save_account_snapshot(args.total, args.cash, stock_value, ratio, pnl)
    print(f"账户快照已保存: 总资产={args.total:.2f} 可用={args.cash:.2f} 仓位={ratio:.1f}% 盈亏={pnl:+.2f}")


def cmd_trade_diagnosis(args):
    """交易诊断"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置，请设置 ZX_LLM_API_KEY 环境变量。")
        return

    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from storage.db import get_db
    from llm.enhancer import diagnose_trade

    print(f"[Diagnosis] 拉取 {args.symbol} K线...")
    candles = ensure_candles(args.symbol, required_days=args.days)
    if len(candles) < 30:
        print(f"K线不足（{len(candles)}天），无法分析")
        return

    result = compute_single(args.symbol, candles)
    if "error" in result:
        print(f"指标计算失败: {result['error']}")
        return

    name = args.name or result.get("name", args.symbol)

    # 获取持仓上下文
    holdings_ctx = ""
    db = get_db()
    pos = db.conn.execute(
        "SELECT total_qty, avg_cost FROM position WHERE code=? AND total_qty > 0",
        (args.symbol,)
    ).fetchone()
    if pos:
        holdings_ctx = f"\n## 当前持仓\n- 持有 {pos[0]} 股\n- 成本价 {pos[1]}\n"

    print(f"[Diagnosis] AI 诊断中...")
    md = diagnose_trade(args.symbol, name, args.action, args.shares, result, holdings_ctx)
    if md:
        print(md)
    else:
        print("LLM 调用失败。")


# ============================================================
# Phase G: 数据报告
# ============================================================

def cmd_data_report(args):
    """个股完整数据报告"""
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from reporting.data_report import build_individual_report
    from data_source.fundamental_cascade import (
        get_fundamentals, get_valuation, get_news_and_reports,
        get_chip, get_fund_flow, get_market_context,
    )
    from llm.market_context import build_sector_context, build_chain_context

    print(f"[Data] 拉取 {args.symbol} K线 + B1指标...")
    candles = ensure_candles(args.symbol, required_days=args.days)
    if len(candles) < 30:
        print(f"K线不足({len(candles)}天)，退出")
        return

    ind = compute_single(args.symbol, candles)
    name = args.name or ind.get("name", args.symbol)

    print("[Data] 基本面...")
    fundamentals = get_fundamentals(args.symbol, name)
    print(f"  源: {fundamentals.get('source','?')}")

    print("[Data] 估值...")
    valuation = get_valuation(args.symbol, name)

    print("[Data] 消息面...")
    news_data = get_news_and_reports(args.symbol)

    print("[Data] 筹码+资金流...")
    chip = get_chip(args.symbol)
    ff = get_fund_flow(args.symbol)

    print("[Data] 市场大局...")
    market = get_market_context()

    sector_ctx = None
    if args.theme:
        print(f"[Data] 产业链定位 ({args.theme})...")
        sector_ctx = build_chain_context(args.theme, args.symbol)
        if sector_ctx:
            print(f"  链条= {sector_ctx['name']}, {sector_ctx['total']}只标的, B1密度={sector_ctx['b1_density']}")
    elif args.sector:
        print(f"[Data] 板块定位 ({args.sector})...")
        sector_ctx = build_sector_context(args.sector, args.symbol)

    print("[Data] 生成报告...")
    md = build_individual_report(args.symbol, name, ind, fundamentals, valuation,
                                 news_data, chip, ff, market, sector_ctx)
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write(md)
        print(f"已保存到 {args.output}")
    else:
        print(md)


def cmd_industry_rebuild(args):
    from config.industry_index import rebuild_ths_index, rebuild_em_index
    if args.source == "ths":
        rebuild_ths_index()
    else:
        rebuild_em_index()


def cmd_industry_lookup(args):
    from config.industry_index import get_tags, get_stocks_by_industry, search_industry, get_industry_path
    if args.search:
        results = search_industry(args.search, args.source)
        print(f"搜索 '{args.search}' ({args.source}): {len(results)} 个匹配")
        for r in results[:20]:
            stocks = get_stocks_by_industry(r, args.source)
            print(f"  {r}: {len(stocks)} 只")
        return
    if args.code:
        tags = get_tags(args.code, args.source)
        path = get_industry_path(args.code, args.source)
        print(f"{args.code} ({args.source}):")
        print(f"  标签: {', '.join(tags) if tags else '(无)'}")
        print(f"  路径: {path}")
        return
    if args.name:
        stocks = get_stocks_by_industry(args.name, args.source)
        print(f"'{args.name}' ({args.source}): {len(stocks)} 只")
        for s in stocks[:15]:
            print(f"  {s}")
        return
    print("请指定 --code / --name / --search")


def cmd_industry_research(args):
    """行业研究 — 任意输入 → LLM 总结 → 保存到 references/industry_logic/

    三种模式:
      1. --urls URL1 URL2    → 抓取URL内容 → LLM总结
      2. --text "文章内容"    → 直接对文本做LLM总结
      3. --stdin              → 从stdin读取（OpenClaw搜索结果传进来）

    OpenClaw 工作流:
      Claude搜索 → 收集文章内容 → python cli.py industry-research --topic PCB --stdin
    """
    from config.llm_config import get_llm_config
    from llm.client import chat

    config = get_llm_config()
    if not config.available:
        print("LLM 未配置。export ZX_LLM_API_KEY=sk-xxx")
        return

    import requests, re, os, sys

    # 1. 收集内容
    content_parts = []

    # --stdin: OpenClaw 把搜索到的内容 pipe 进来
    if args.stdin:
        if not sys.stdin.isatty():
            stdin_text = sys.stdin.read().strip()
            if stdin_text:
                content_parts.append(stdin_text)
                print(f"  从 stdin 读取: {len(stdin_text)} chars")

    if args.urls:
        for url in args.urls:
            try:
                headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
                r = requests.get(url, headers=headers, timeout=30)
                if r.status_code == 200:
                    text = r.text
                    text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<style[^>]*>.*?</style>', '', text, flags=re.DOTALL)
                    text = re.sub(r'<[^>]+>', ' ', text)
                    text = re.sub(r'\s+', ' ', text).strip()
                    content_parts.append(f"来源: {url}\n\n{text[:6000]}")
                    print(f"  {url[:60]}... OK ({len(text)} chars)")
                else:
                    print(f"  {url[:60]}... HTTP {r.status_code}")
            except Exception as e:
                print(f"  {url[:60]}... {e}")

    if args.text:
        content_parts.append(args.text)

    if not content_parts:
        print("无可用内容。请提供 --urls、--text 或 --stdin")
        return

    # 2. LLM 总结
    print(f"\n[LLM] 总结 {args.topic} 行业逻辑...")
    combined = "\n\n---\n\n".join(content_parts)

    messages = [
        {"role": "system", "content": f"""你是A股行业研究员。请从以下文章中提取{args.topic}行业的投资逻辑。
输出格式（Markdown）：
## {args.topic}行业逻辑
### 一、行业现状（市场规模、增速、技术阶段）
### 二、产业链结构（上游/中游/下游，各环节核心A股标的及代码）
### 三、核心驱动（需求端/技术变革/政策）
### 四、投资主线（按确定性排序）
### 五、重点关注标的（| 代码 | 名称 | 环节 | 逻辑 |）
### 六、风险"""},
        {"role": "user", "content": combined},
    ]

    resp = chat(messages, max_tokens=4096)
    if not resp:
        print("LLM 调用失败")
        return

    # 3. 保存
    ref_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "industry_logic")
    os.makedirs(ref_dir, exist_ok=True)
    output_path = args.output or os.path.join(ref_dir, f"{args.topic}_行业逻辑.md")

    header = f"> 自动生成 | 来源: {', '.join(args.urls or ['stdin/text'])}\n\n"
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(header + resp["content"])
    print(f"\n已保存: {output_path}")


def cmd_kline_analyze(args):
    """K线综合分析（LLM）"""
    from config.llm_config import get_llm_config
    config = get_llm_config()
    if not config.available:
        print("LLM 未配置。export ZX_LLM_API_KEY=sk-xxx")
        return

    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from llm.kline_preprocessor import preprocess_kline
    from llm.client import chat
    from llm.prompts.kline_analysis import build_prompt
    from data_source.fundamental_cascade import get_fundamentals, get_chip
    from reporting.data_report import _fmt, _fmt_pct as fpct, _fmt_amount as famt

    print(f"[Analyze] {args.symbol} K线 + B1...")
    candles = ensure_candles(args.symbol, required_days=args.days)
    if len(candles) < 30:
        print(f"K线不足({len(candles)}天)")
        return
    ind = compute_single(args.symbol, candles)
    name = args.name or ind.get("name", args.symbol)

    print("[Analyze] 预处理K线形态...")
    kline_ctx = preprocess_kline(candles, ind, lookback=20)

    print("[Analyze] 基本面...")
    fund = get_fundamentals(args.symbol, name)
    fund_str = ""
    if fund and fund.get("source") != "none":
        fund_str = f"""## 基本面
| 指标 | 数值 |
|------|------|
| 营收 | {famt(fund.get('revenue'))} | 净利润 | {famt(fund.get('net_profit'))} |
| ROE | {fpct(fund.get('roe'))} | 毛利率 | {fpct(fund.get('gross_margin'))} |
| 质量: {fund.get('quality',{}).get('profit_quality','?')}"""

    chip = get_chip(args.symbol)
    chip_str = ""
    if chip:
        chip_str = f"""## 筹码
| 获利比例 | {chip.get('profit_ratio',0)*100:.1f}% | 成本 | {chip.get('avg_cost','?')} |
| 90%集中度 | {chip.get('concentration_90',0)*100:.1f}% | 状态 | {chip.get('chip_status','?')} |"""

    theme_str = ""
    if args.theme:
        from llm.market_context import build_chain_context
        chain = build_chain_context(args.theme, args.symbol)
        if chain:
            theme_str = f"## 产业链: {args.theme}\n- 对标标的: {chain.get('total','?')}只\n- 该股所在环节: {chain.get('target_sub','?')}"
        # 自动加载已保存的行业逻辑
        try:
            from llm.industry_research import get_industry_logic
            logic = get_industry_logic(args.theme)
            if logic:
                theme_str += f"\n\n## {args.theme}行业逻辑（知识库）\n{logic[:2000]}"
        except Exception:
            pass

    verify_report = ""
    if args.verify:
        print("[Analyze] 交叉验证K线...")
        from data_source.kline_verifier import KlineVerifier
        verifier = KlineVerifier()
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
        v = verifier.verify(args.symbol, start, end, candles)
        if v.get("match") is not None:
            status = "✅ 一致" if v["match"] else f"⚠️ {len(v.get('discrepancies',[]))}处差异"
            verify_report = f"""## K线交叉验证 ({v.get('source','?')})
| 指标 | 数值 |
|------|------|
| 对比源 | {v.get('source','?')} |
| 共同日期 | {v.get('common_dates','?')}天 |
| 收盘价相关系数 | {v.get('correlation','?')} |
| 平均价差 | {v.get('avg_close_diff','?')}% |
| 结论 | {status} |"""
            if v.get("discrepancies"):
                verify_report += "\n### 差异明细\n| 日期 | 类型 | 主源 | 备源 | 差异% |\n|------|------|------|------|-------|\n"
                for d in v["discrepancies"][:5]:
                    verify_report += f"| {d['date']} | {d['type']} | {d['primary']} | {d['secondary']} | {d['diff_pct']}% |\n"
        else:
            verify_report = "## K线交叉验证\n*无可用的备选验证源*"

    print("[Analyze] LLM 分析中...")
    messages = build_prompt(name, args.symbol, kline_ctx, fund_str, theme_str, chip_ctx=chip_str, news_ctx=verify_report)
    resp = chat(messages, max_tokens=4096)
    if resp:
        md = f"# {name}({args.symbol}) K线综合分析\n\n{resp['content']}\n\n---\n*模型: {resp['model']} | tokens: {resp['tokens_in']}/{resp['tokens_out']}*"
        if args.output:
            with open(args.output, 'w', encoding='utf-8') as f:
                f.write(md)
            print(f"已保存到 {args.output}")
        else:
            print(md)
    else:
        print("LLM 调用失败")


def cmd_sector_report(args):
    """板块扫描数据报告"""
    from scanning.sector_scanner import SectorOverview, SectorB1Scanner
    from reporting.data_report import build_individual_report
    from data_source.fundamental_cascade import get_market_context
    from indicators.b1_calculator import compute_single
    from storage.kline_filler import ensure_candles

    print(f"[Sector] 概览 + B1扫描 '{args.name}'...")
    scanner = SectorB1Scanner(workers=args.workers)
    combined = scanner.scan(args.name, days=args.days)
    ov = combined.get("overview")
    b1 = combined.get("b1")
    if not b1 or not b1.stocks:
        print("无扫描结果")
        return

    print("[Sector] 市场大局...")
    market = get_market_context()

    # 生成报告头
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = []
    L = lines.append
    L(f"# {args.name} 板块扫描报告")
    L(f"> {now}  {ov.total_stocks if ov else '?'}只成分股  B1={len(b1.b1_stocks)} 近B1={len(b1.near_b1_stocks)} 趋势={len(b1.trend_hold_stocks)}")

    # 市场大局
    from reporting.data_report import _section_market
    _section_market(lines, market)

    # 重点标的表格：龙头 + B1 + 领涨 三列合表
    L("## 重点标的")
    L("")
    L("| 名称代码 | 主导业务 | 板块地位 | 涨跌 | B1状态 | J值 | 评分 | 信号 |")
    L("|----------|---------|---------|------|--------|-----|------|------|")
    # 合并 ov 概览数据和 b1 指标
    ov_map = {}
    if ov:
        for s in ov.stocks:
            ov_map[getattr(s, 'code', '')] = s

    for s in sorted(b1.stocks, key=lambda x: (len(getattr(x, '信号', []) or []), getattr(x, '评分', 0)), reverse=True)[:25]:
        sig_str = "+".join(getattr(s, '信号', [])) or "—"
        b1_status = "★B1" if (getattr(s, '信号', None) or getattr(s, '基础B1', None)) else ("近B1" if getattr(s, 'J', 99) < 20 else getattr(s, '趋势', ''))
        ov_s = ov_map.get(s.code)
        biz = _get_biz(s.code, ov, 30) if ov else ""
        tag = ""
        if ov_s:
            if getattr(ov_s, 'leader_tag', ''): tag = f"🐉{ov_s.leader_tag[:6]}"
            elif abs(getattr(ov_s, 'change_pct', 0)) >= 5: tag = "领涨" if getattr(ov_s, 'change_pct', 0) > 0 else "领跌"
        change = getattr(ov_s, 'change_pct', getattr(s, 'change_pct', 0)) if ov_s else getattr(s, 'change_pct', 0)
        L(f"| {s.name}({s.code}) | {biz} | {tag} | {change:+.1f}% | {b1_status} | {getattr(s,'J','?')} | {getattr(s,'评分','?')} | {sig_str} |")

    L("")
    L(f"**B1标段({len(b1.b1_stocks)}只)**: {', '.join(f'{s.name}({s.code})' for s in b1.b1_stocks[:15])}")
    L(f"\n**近B1观察({len(b1.near_b1_stocks)}只)**: {', '.join(f'{s.name}({s.code})' for s in b1.near_b1_stocks[:10])}")
    L("")

    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            f.write("\n".join(lines))
        print(f"已保存到 {args.output}")
    else:
        print("\n".join(lines))


def _get_biz(code, ov, max_len=60):
    """从概览数据取主营业务"""
    if not ov:
        return ""
    for s in ov.stocks:
        if getattr(s, 'code', '') == code:
            biz = getattr(s, 'business', '') or getattr(s, '主营产品名称', '')
            return biz[:max_len] if biz else ""
    return ""


def _get_all_stock_codes(force_refresh: bool = False) -> tuple:
    """获取全市场A股代码+名称列表，本地缓存优先。返回 (codes, names_dict)。
    force_refresh 时重新从远程拉取并更新缓存。"""
    from storage.db import get_db
    db = get_db()

    # 1. 本地缓存
    if not force_refresh:
        rows = db.conn.execute("SELECT code, name FROM stock_info").fetchall()
        if rows:
            codes = [r[0] for r in rows]
            names = {r[0]: r[1] for r in rows}
            return codes, names

    # 2. baostock 行业分类（含名称）
    codes, names = _try_baostock_stock_list()
    if not codes:
        # 3. akshare 全量
        codes, names = _try_akshare_stock_list()

    # 4. 写入缓存
    if codes:
        now = __import__('datetime').datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        db.conn.execute("DELETE FROM stock_info")
        for c in codes:
            db.conn.execute(
                "INSERT OR REPLACE INTO stock_info(code,name,updated_at) VALUES(?,?,?)",
                (c, names.get(c, ""), now))
        db.conn.commit()
    return codes, names


def _try_baostock_stock_list() -> tuple:
    try:
        import baostock as bs
        bs.login()
        rs = bs.query_stock_industry()
        codes, names = [], {}
        while (rs.error_code == '0') and rs.next():
            r = rs.get_row_data()
            code = r[1].replace("sh.", "").replace("sz.", "").replace("bj.", "")
            if code.isdigit() and len(code) == 6:
                codes.append(code)
                names[code] = r[2]
        bs.logout()
        if codes:
            codes = list(dict.fromkeys(codes))
            print(f"  [stock_list] baostock: {len(codes)} 只")
        return codes, names
    except Exception:
        return [], {}


def _try_akshare_stock_list() -> tuple:
    try:
        import akshare as ak
        df = ak.stock_info_a_code_name()
        codes = [str(c) for c in df["code"].tolist()]
        names = dict(zip(codes, df["name"].tolist()))
        print(f"  [stock_list] akshare: {len(codes)} 只")
        return codes, names
    except Exception:
        return [], {}


def cmd_kline_update(args):
    """更新K线数据到数据库"""
    from storage.kline_filler import ensure_candles

    codes = []
    if args.code:
        codes = [args.code]
    elif args.market:
        from config.blacklist import blacklist as bl
        print(f"[Kline Update] 获取全市场股票列表...")
        print(f"  {bl.summary()}")
        all_codes, name_map = _get_all_stock_codes()
        codes = [c for c in all_codes if not bl.is_banned(c, name_map.get(c, ""))]
        print(f"[Kline Update] 全市场（过滤后）: {len(codes)} 只")
    elif args.sector:
        from data_source.sector_store import get_sector_members, update_sector
        print(f"[Kline Update] 先更新板块 '{args.sector}' 的成分股...")
        update_sector(args.sector)
        members = get_sector_members(args.sector)
        codes = [m["code"] for m in members]
        if not codes:
            print("板块无成分股缓存，请先运行 sector-update")
            return
        print(f"[Kline Update] 板块 '{args.sector}': {len(codes)} 只成分股")
    elif args.all:
        from storage.db import get_db
        db = get_db()
        codes = [r[0] for r in db.conn.execute("SELECT DISTINCT code FROM stock_daily").fetchall()]
        print(f"[Kline Update] 全部: {len(codes)} 只")
    else:
        print("请指定 --code / --sector / --all / --market")
        return

    scan_id = None
    if args.add_watchlist:
        from storage.portfolio_db import record_b1_scan
        scan_id = record_b1_scan("market", "全市场扫描", len(codes), 0, 0, "", 0)

    b1_results = []
    b1_count = near_count = err_count = 0
    for i, code in enumerate(codes):
        if i % 100 == 0:
            print(f"  [{i+1}/{len(codes)}] B1:{b1_count} 近B1:{near_count} err:{err_count}")
        candles = ensure_candles(code, required_days=args.days)
        if not candles or len(candles) < args.days:
            err_count += 1
            continue
        from indicators.b1_calculator import compute_single
        ind = compute_single(code, candles)
        if not ind or ind.get("error"):
            err_count += 1
            continue
        sj = ind.get("信号", [])
        is_b1 = bool(sj or ind.get("基础B1"))
        is_near = (not is_b1) and (ind.get("J") or 999) < 20

        entry = {"code": code, "J": ind.get("J"), "评分": ind.get("评分"),
                 "趋势": ind.get("趋势"), "B1": is_b1, "信号": sj}
        b1_results.append(entry)

        if is_b1:
            b1_count += 1
            if args.add_watchlist and scan_id:
                from storage.portfolio_db import add_to_watchlist, add_b1_candidate, record_watchlist_daily
                name = ind.get("name", code)
                add_to_watchlist(code, "", source="market_scan", reason="全市场B1", tags=["B1"], level=1)
                add_b1_candidate(scan_id, code, "", "全市场", "B1", ind)
                record_watchlist_daily(code, ind)
        elif is_near:
            near_count += 1
            if args.add_watchlist and scan_id:
                from storage.portfolio_db import add_to_watchlist, add_b1_candidate, record_watchlist_daily
                add_to_watchlist(code, "", source="market_scan", reason="全市场近B1", tags=["近B1"])
                add_b1_candidate(scan_id, code, "", "全市场", "near_B1", ind)
                record_watchlist_daily(code, ind)

    if scan_id and (b1_count + near_count > 0):
        from storage.db import get_db
        db = get_db()
        db.conn.execute("UPDATE b1_scan SET b1_count=?, near_b1_count=? WHERE scan_id=?",
                        (b1_count, near_count, scan_id))
        db.conn.commit()

    print(f"\n===== 扫描完成 =====")
    print(f"总数:{len(codes)} B1:{b1_count} 近B1(J<20):{near_count} 错误/数据不足:{err_count}")
    if b1_count > 0:
        b1s = [r for r in b1_results if r["B1"]]
        print(f"\n★ B1 ({b1_count}只, top20):")
        for r in sorted(b1s, key=lambda x: -(x["评分"] or 0))[:20]:
            print(f"  {r['code']}: J={r['J']:.1f} 评分={r['评分']} {r['趋势']} [{','.join(r['信号'][:3]) or '-'}]")
    if near_count > 0 and near_count <= 50:
        nears = [r for r in b1_results if not r["B1"]]
        print(f"\n△ 近B1({near_count}只, top15):")
        for r in sorted(nears, key=lambda x: x["J"] or 999)[:15]:
            print(f"  {r['code']}: J={r['J']:.1f} 评分={r['评分']}")


def cmd_sector_update(args):
    """更新东财板块成分股缓存"""
    from data_source.sector_store import update_sector, update_all_from_theme_chains, get_sector_members

    if args.all:
        print("[Sector Update] 全量更新 theme_chains 板块...")
        total = update_all_from_theme_chains()
        print(f"完成: {total} 条")
        return

    if args.name:
        print(f"[Sector Update] 更新 '{args.name}' ({args.type}) ...")
        n = update_sector(args.name, kind=args.type)
        print(f"完成: {n} 条")
        members = get_sector_members(args.name, kind=args.type)
        if members:
            print(f"前5只: {', '.join(f'{m['code']} {m['name']}' for m in members[:5])}")
        return

    print("请指定 --name / --all")


def cmd_daily_update(args):
    """日更全流程：K线同步 → B1扫描 → 趋势追踪 → 关注列表分层"""
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout,'buffer') else sys.stdout

    from storage.db import get_db
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from indicators.trend_analyzer import TrendAnalyzer
    from indicators.suo_bao_b1 import scan as suo_bao_scan
    from storage.portfolio_db import add_to_watchlist, record_watchlist_daily
    from tracking.trend_tracker import daily_trend_update

    db = get_db()
    db.ensure_trading_calendar()
    today = db.conn.execute("SELECT MAX(date) FROM trading_calendar").fetchone()[0]

    # Step 1: 关注+持仓列表
    codes = set()
    for (c,) in db.conn.execute("SELECT DISTINCT code FROM watchlist WHERE status='active'").fetchall():
        codes.add(c)
    for (c,) in db.conn.execute("SELECT DISTINCT code FROM position").fetchall():
        codes.add(c)
    codes = sorted(codes)
    print(f"[日更] {today} | {len(codes)}只")

    # Step 2: 补K线(增量)
    ok = fail = 0
    for i, c in enumerate(codes):
        if i % 50 == 0:
            print(f"  K线[{i+1}/{len(codes)}] ok={ok} fail={fail}")
        rows = ensure_candles(c, required_days=args.days)
        if rows and len(rows) >= 110:
            ok += 1
        else:
            fail += 1
    print(f"  K线: ok={ok} fail={fail}")

    # Step 3: B1+趋势+缩爆
    names = {r[0]: r[1] for r in db.conn.execute("SELECT code,name FROM stock_info").fetchall()}
    b1l, nearl, tre_l2, tre_l1, errl = [], [], [], [], []
    for c in codes:
        rows = db.get_candles(c, 250)
        if not rows or len(rows) < 110:
            errl.append(c)
            continue
        ind = compute_single(c, rows)
        if not ind or ind.get("error"):
            errl.append(c)
            continue
        # B1
        sj = ind.get("信号", [])
        j = ind.get("J", 999)
        if sj or ind.get("基础B1"):
            b1l.append({"code": c, "name": names.get(c, ""), "J": round(j, 1) if j else 0,
                        "RSI": round(ind.get("RSI", 0), 1), "信号": sj})
        elif j < 20:
            nearl.append({"code": c, "name": names.get(c, ""), "J": round(j, 1) if j else 0})

        # 趋势
        t = TrendAnalyzer(c, rows).compute()
        if "error" in t:
            continue
        if t["cross"] == "golden":
            tre_l1.append({"code": c, "name": names.get(c, ""), "state": t["state"],
                           "score": t["score"], "slope_ratio": t["斜率比"]})
        elif t["state"] == "拐头向上":
            tre_l2.append({"code": c, "name": names.get(c, ""), "state": t["state"],
                           "score": t["score"], "slope_ratio": t["斜率比"]})

    # Step 4: 趋势状态转移 + 分层入库
    trend_result = daily_trend_update(codes)

    # B1→level=1, 近B1→level=2
    for e in b1l:
        add_to_watchlist(e["code"], e["name"], source="daily", reason="B1", tags=["B1"], level=1)
    for e in nearl:
        add_to_watchlist(e["code"], e["name"], source="daily", reason="近B1", tags=["近B1"], level=2)

    # Step 5: B1入库b1_candidate（market report需要用）
    from storage.portfolio_db import record_b1_scan, add_b1_candidate
    scan_id = record_b1_scan("daily", today, len(codes), len(b1l), len(nearl), "", 0)
    for e in b1l:
        add_b1_candidate(scan_id, e["code"], e["name"], "日更", "B1", e)
    for e in nearl:
        add_b1_candidate(scan_id, e["code"], e["name"], "日更", "near_B1", e)

    # Step 6: 输出
    print(f"\n=== 日更结果 ===")
    print(f"★B1: {len(b1l)}只  △近B1: {len(nearl)}只")
    print(f"趋势金叉→重点: {len(tre_l1)}只  趋势拐头向上→普通: {len(tre_l2)}只")
    print(f"状态转移: {len(trend_result['transitions'])}条")
    for tr in trend_result["transitions"][:15]:
        print(f"  {tr['code']} {tr['prev']}→{tr['curr']}: {tr['reason']}")
    if tre_l1:
        items = [e['code'] + '(' + str(e['score']) + ')' for e in tre_l1]
        print(f"\n★ 金叉(重点): {', '.join(items)}")
    if tre_l2:
        items2 = [e['code'] + '(' + str(e['score']) + ')' for e in tre_l2[:10]]
        print(f"△ 拐头向上(普通): {', '.join(items2)}")
    t = db.conn.execute("SELECT COUNT(*) FROM watchlist WHERE status='active'").fetchone()[0]
    l1 = db.conn.execute("SELECT COUNT(*) FROM watchlist WHERE status='active' AND level=1").fetchone()[0]
    l2 = db.conn.execute("SELECT COUNT(*) FROM watchlist WHERE status='active' AND level=2").fetchone()[0]
    print(f"\n关注列表: {t}只 (重点{l1} 普通{l2})")


def cmd_trend(args):
    """知行趋势指标分析"""
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout,'buffer') else sys.stdout
    from storage.kline_filler import ensure_candles
    from indicators.trend_analyzer import TrendAnalyzer

    print(f"[Trend] 拉取 {args.symbol} K线...")
    candles = ensure_candles(args.symbol, required_days=args.days)
    if not candles or len(candles) < 110:
        print(f"K线不足 ({len(candles) if candles else 0}天)")
        return

    ta = TrendAnalyzer(args.symbol, candles)
    r = ta.compute()
    if "error" in r:
        print(f"计算失败: {r['error']}")
        return

    print(f"\n{'='*60}")
    print(f"  知行趋势 — {args.symbol}")
    print(f"{'='*60}")
    print(f"  白线(短期): {r['白']:.3f}    黄线(中长期): {r['黄']:.3f}")
    print(f"  差值: {r['差值_pct']:.1f}% (白{'上' if r['差值_pct']>0 else '下'}黄)")
    print(f"  白线今日变化率: {r['白_slope_1d']:+.3f}%    黄线5日趋势: {r['黄_slope_5d']:+.3f}%")
    print(f"  差值趋势: {r['差值_trend']}  ({r['差值_growth']:+.1f}%)")
    cross_info = r['cross'] or "无" if r['cross_days'] == 0 else f"{r['cross']} ({r['cross_days']}天前)"
    print(f"  穿越: {cross_info}")
    print(f"  拐点: {r['inflection'] or '无'}")
    print(f"  状态: {r['state']}")
    print(f"  综合评分: {r['score']}/10")
    print(f"  信号: {', '.join(r['signals'])}")


def cmd_quote(args):
    """实时行情查询"""
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout,'buffer') else sys.stdout

    from data_source.quote_fetcher import QuoteFetcher
    qf = QuoteFetcher()

    if args.symbol:
        print(f"查询 {args.symbol} ...")
        q = qf.get_quote(args.symbol)
        if q:
            _print_quote(q)
        else:
            print("查询失败")

    elif args.holdings:
        from storage.portfolio_db import list_positions
        positions = list_positions()
        if not positions:
            print("无持仓")
            return
        codes = [p["code"] for p in positions]
        print(f"持仓行情 ({len(codes)}只)...")
        for c in codes:
            q = qf.get_quote(c)
            if q:
                _print_quote_line(q)
            else:
                print(f"  {c}: 查询失败")

    elif args.watch:
        from storage.portfolio_db import list_watchlist
        watchers = list_watchlist("active")
        if not watchers:
            print("无活跃关注")
            return
        codes = [w["code"] for w in watchers]
        print(f"关注行情 ({len(codes)}只)...")
        for c in codes:
            q = qf.get_quote(c)
            if q:
                _print_quote_line(q)
            else:
                print(f"  {c}: 查询失败")

    elif args.index:
        print("主要指数行情...")
        quotes = qf.get_index_quotes()
        for q in quotes:
            chg = q.get("change_pct", 0) or 0
            print(f"  {q['name']}({q['code']}): {q.get('price','?')} ({chg:+.2f}%)")

    else:
        print("请指定 --symbol / --holdings / --watch / --index")


def _print_quote(q):
    """打印完整行情"""
    print(f"{'='*60}")
    print(f"  {q.get('name','?')}({q.get('code','?')})")
    print(f"  最新价: {q.get('price','?')}  ({q.get('change_pct',0):+.2f}%)")
    print(f"  今开: {q.get('open','?')}  最高: {q.get('high','?')}  最低: {q.get('low','?')}")
    if q.get('volume'):
        print(f"  成交量: {q['volume']:.0f}  成交额: {q.get('amount',0):.2f}")
    if q.get('pe'):
        print(f"  PE: {q['pe']:.1f}  PB: {q.get('pb','?'):.1f}")
    if q.get('volume_ratio'):
        print(f"  量比: {q['volume_ratio']:.2f}  换手率: {q.get('turnover_rate','?'):.2f}%")
    if q.get('total_mv'):
        print(f"  总市值: {q['total_mv']:.0f}")
    print(f"  数据源: {q.get('source','?')}")


def _print_quote_line(q):
    """单行行情"""
    chg = q.get("change_pct", 0) or 0
    sign = "🔴" if chg < 0 else ("🟢" if chg > 0 else "⚪")
    print(f"  {sign} {q.get('name','?'):<8s} {q.get('price','?'):>8} ({chg:+.2f}%)")


def cmd_scan(args):
    """选股引擎：B1+缩量爆发。数据不足自动补缺。"""
    from storage.kline_filler import ensure_candles
    from config.blacklist import blacklist as bl
    from storage.portfolio_db import add_to_watchlist, add_b1_candidate, record_b1_scan, record_watchlist_daily

    codes = []
    label = ""
    if args.codes:
        codes = [c.strip() for c in args.codes.split(",") if c.strip()]
        label = f"指定列表({len(codes)}只)"
    elif args.market:
        all_codes, name_map = _get_all_stock_codes()
        codes = [c for c in all_codes if not bl.is_banned(c, name_map.get(c, ""))]
        label = f"全市场({len(codes)}只)"
    elif args.sector:
        from data_source.sector_store import get_sector_members, update_sector
        update_sector(args.sector)
        members = get_sector_members(args.sector)
        codes = [m["code"] for m in members]
        label = f"板块'{args.sector}'({len(codes)}只)"
    else:
        print("请指定 --name / --market / --codes")
        return

    print(f"[Scan] {label}")
    scan_id = None
    if args.auto_save:
        scan_id = record_b1_scan("scan", label, len(codes), 0, 0, "", 0)

    b1_count = near_count = err_count = 0
    for i, code in enumerate(codes):
        if i % 50 == 0:
            print(f"  [{i+1}/{len(codes)}] B1:{b1_count} 近B1:{near_count} err:{err_count}")
        candles = ensure_candles(code, required_days=args.days)
        if not candles or len(candles) < args.days:
            err_count += 1
            continue
        from indicators.b1_calculator import compute_single
        from indicators.suo_bao_b1 import scan as suo_bao_scan
        ind = compute_single(code, candles)
        if not ind or ind.get("error"):
            err_count += 1
            continue
        sb = suo_bao_scan(code, "", candles)
        sj = ind.get("信号", [])
        is_b1 = bool(sj or ind.get("基础B1"))
        is_near = (not is_b1) and (ind.get("J") or 999) < 20
        suo = sb.get("ok", False) if isinstance(sb, dict) else bool(sb)

        if is_b1:
            b1_count += 1
            if args.auto_save and scan_id:
                add_to_watchlist(code, "", source="scan", reason="B1", tags=["B1"], level=1)
                add_b1_candidate(scan_id, code, "", label, "B1", ind)
                record_watchlist_daily(code, ind)
        elif is_near:
            near_count += 1
            if args.auto_save and scan_id:
                add_to_watchlist(code, "", source="scan", reason="近B1", tags=["近B1"], level=2)
                add_b1_candidate(scan_id, code, "", label, "near_B1", ind)
                record_watchlist_daily(code, ind)
        if suo:
            if args.auto_save and scan_id:
                add_to_watchlist(code, "", source="scan", reason="缩量爆发", tags=["缩爆"], level=1)

    from storage.db import get_db
    if scan_id and (b1_count + near_count > 0):
        db = get_db()
        db.conn.execute("UPDATE b1_scan SET b1_count=?, near_b1_count=? WHERE scan_id=?", (b1_count, near_count, scan_id))
        db.conn.commit()

    print(f"\n===== 选股结果 =====")
    print(f"总数:{len(codes)} ★B1:{b1_count} △近B1(J<20):{near_count} 错误/数据不足:{err_count}")
    if b1_count > 0:
        print(f"★ B1 已入库重点关注")
    if near_count > 0:
        print(f"△ 近B1 已入库普通关注")


def cmd_data(args):
    """data 命令分发"""
    if not hasattr(args, 'data_cmd') or not args.data_cmd:
        print("请指定子命令: data sync --target kline|index|calendar")
        return
    if args.data_cmd == "sync":
        _cmd_data_sync(args)


def cmd_find(args):
    """智能选股 — 精确板块/模糊语义 → scan"""
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout,'buffer') else sys.stdout

    # Step 1: 解析 query → 行业列表
    sectors = []
    if args.name:
        from config.theme_chains import resolve_sector as rs
        concept, industry = rs(args.name)
        if concept:
            sectors = [{"name": concept, "type": "concept", "reason": "精确指定"}]
        elif industry:
            sectors = [{"name": industry, "type": "industry", "reason": "精确指定"}]
        else:
            # 不在映射表里，直接当行业名
            sectors = [{"name": args.name, "type": "concept", "reason": "直接使用"}]
    elif args.query:
        print(f"[Find] 解析: {args.query}")
        try:
            from llm.router import resolve_query_to_sectors
            result = resolve_query_to_sectors(args.query)
            if result and result.get("sectors"):
                sectors = result["sectors"]
                print(f"  {result.get('summary', '')}")
            else:
                print("  未能解析到行业，请用更具体的描述")
                return
        except Exception as e:
            print(f"  LLM 解析失败: {e}")
            print("  请用 --name 指定精确板块名")
            return
    else:
        print("请指定 --name 板块名 或 query")
        return

    # Step 2: 对每个行业取成分股
    from data_source.sector_store import get_sector_members, update_sector
    from config.blacklist import blacklist as bl
    print(f"  找到 {len(sectors)} 个板块:")
    all_codes = []
    for s in sectors:
        n = s["name"]
        print(f"    {n} ({s['type']}): {s['reason']}")
        # 尝试从缓存取，失败则实时拉
        members = get_sector_members(n, kind=s["type"])
        if not members:
            print(f"      缓存为空，实时拉取...")
            n2 = update_sector(n, kind=s["type"])
            members = get_sector_members(n, kind=s["type"])
        if members:
            for m in members:
                if not bl.is_banned(m["code"], m.get("name", "")):
                    all_codes.append(m["code"])
            print(f"      {len(members)}只成分股")
        else:
            print(f"      无成分股数据")

    all_codes = list(set(all_codes))
    if not all_codes:
        print("  未能获取任何成分股")
        return
    print(f"\n  共 {len(all_codes)} 只待扫描")

    # Step 3: 扫描
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single
    from indicators.trend_analyzer import TrendAnalyzer
    from storage.portfolio_db import add_to_watchlist
    from storage.db import get_db
    db = get_db()
    names = {r[0]: r[1] for r in db.conn.execute("SELECT code,name FROM stock_info").fetchall()}

    b1l, tre_l1, tre_l2, err = [], [], [], 0
    for i, c in enumerate(all_codes):
        candles = ensure_candles(c, 125)
        if not candles or len(candles) < 110:
            err += 1
            continue
        ind = compute_single(c, candles)
        if not ind or ind.get("error"):
            err += 1
            continue
        # B1
        sj = ind.get("信号", [])
        j = ind.get("J", 999)
        if sj or ind.get("基础B1"):
            b1l.append({"code": c, "name": names.get(c, ""), "J": round(j, 1) if j else 0,
                        "信号": sj})
            add_to_watchlist(c, names.get(c, ""), source="find", reason="B1", level=1)
        # 趋势
        t = TrendAnalyzer(c, candles).compute()
        if "error" in t:
            continue
        if t["cross"] == "golden":
            tre_l1.append({"code": c, "name": names.get(c, ""), "state": t["state"], "score": t["score"]})
            add_to_watchlist(c, names.get(c, ""), source="find", reason="金叉", level=1)
        elif t["state"] == "拐头向上":
            tre_l2.append({"code": c, "name": names.get(c, ""), "score": t["score"]})
            add_to_watchlist(c, names.get(c, ""), source="find", reason="拐头向上", level=2)

    # Step 4: 输出
    print(f"\n=== 选股结果 ===")
    print(f"★B1: {len(b1l)}只  |  趋势金叉: {len(tre_l1)}只  |  拐头向上: {len(tre_l2)}只  |  错误: {err}")
    if b1l:
        print(f"\n★ B1信号:")
        for r in sorted(b1l, key=lambda x: x["J"]):
            sigs = ",".join(r["信号"][:2]) if r["信号"] else "-"
            print(f"  {r['code']} {r['name']}: J={r['J']:.1f} [{sigs}]")
    if tre_l1:
        print(f"\n★ 金叉(重点): {(', '.join(e['code']+'('+str(e['score'])+')' for e in tre_l1))}")
    if tre_l2:
        print(f"\n△ 拐头向上(普通): {(', '.join(e['code']+'('+str(e['score'])+')' for e in tre_l2[:10]))}")


def cmd_market_report(args):
    """市场环境报告 — DB数据 + Tavily WebSearch + LLM整合 → MD存档 → 飞书"""
    import sys, io, os
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8') if hasattr(sys.stdout,'buffer') else sys.stdout
    from datetime import datetime

    # ==========================================
    # 1. 数据聚合（从DB读）
    # ==========================================
    from storage.db import get_db
    db = get_db()
    db.ensure_trading_calendar()
    # 报告日期 = 最近一个交易日（凌晨执行时取前一日）
    date_str = db.conn.execute("SELECT MAX(date) FROM trading_calendar WHERE date<=date('now')").fetchone()[0]

    # 指数（从 index_daily 读收盘数据）
    from data_source.quote_fetcher import TRACKED_INDEXES
    quotes = []
    for code, name in TRACKED_INDEXES.items():
        row = db.conn.execute(
            "SELECT close, change_pct FROM index_daily WHERE code=? AND date<=? ORDER BY date DESC LIMIT 1",
            (code, date_str)
        ).fetchone()
        if row and row[0]:
            quotes.append({"code": code, "name": name, "price": row[0], "change_pct": row[1] or 0, "source": "db"})
        else:
            quotes.append({"code": code, "name": name, "price": 0, "change_pct": 0, "source": "none"})

    # B1
    scan = db.conn.execute("SELECT b1_count, near_b1_count FROM b1_scan ORDER BY scan_id DESC LIMIT 1").fetchone()
    b1_count = scan[0] if scan else 0
    near_count = scan[1] if scan else 0
    wl_l1 = db.conn.execute("SELECT COUNT(*) FROM watchlist WHERE level=1 AND status='active'").fetchone()[0]
    wl_l2 = db.conn.execute("SELECT COUNT(*) FROM watchlist WHERE level=2 AND status='active'").fetchone()[0]

    # 板块排名：取实际有candidate记录的最新批次
    sector_b1 = {}
    scan_id = db.conn.execute(
        "SELECT scan_id FROM b1_scan WHERE b1_count>0 "
        "AND (SELECT COUNT(*) FROM b1_candidate WHERE scan_id=b1_scan.scan_id AND category='B1')>0 "
        "ORDER BY scan_id DESC LIMIT 1"
    ).fetchone()
    if scan_id and scan_id[0]:
        for r in db.conn.execute(
            "SELECT si.sector_name, COUNT(*) as cnt FROM b1_candidate bc "
            "LEFT JOIN sector_index si ON bc.code=si.code "
            f"WHERE bc.scan_id={scan_id[0]} AND bc.category='B1' "
            "GROUP BY si.sector_name ORDER BY cnt DESC LIMIT 15"
        ).fetchall():
            sector_b1[r[0] or "未分类"] = r[1]

    # B1变化（新进/消失）
    new_b1 = []
    sids = [r[0] for r in db.conn.execute("SELECT DISTINCT scan_id FROM b1_scan WHERE b1_count>0 ORDER BY scan_id DESC LIMIT 2").fetchall()]
    if len(sids) >= 2:
        curr = {r[0] for r in db.conn.execute(f"SELECT DISTINCT code FROM b1_candidate WHERE scan_id={sids[0]} AND category='B1'").fetchall()}
        prev = {r[0] for r in db.conn.execute(f"SELECT DISTINCT code FROM b1_candidate WHERE scan_id={sids[1]} AND category='B1'").fetchall()}
        new_b1 = list(curr - prev)

    # 历史上下文
    base_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "references", "market_journal")
    os.makedirs(base_dir, exist_ok=True)
    history = ""
    import glob
    for f in sorted(glob.glob(os.path.join(base_dir, "2026-*.md")))[-3:]:
        try:
            with open(f, 'r', encoding='utf-8') as fp:
                history += fp.read()[:2000] + "\n---\n"
        except Exception:
            pass

    # ==========================================
    # 2. Web Search (Tavily)
    # ==========================================
    search_text = ""
    if not args.no_search:
        os.environ.setdefault("TAVILY_API_KEY", "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")
        try:
            from data_source.web_search import get_market_news, get_sector_news
            mn = get_market_news()
            if mn:
                search_text += "### 今日热点\n" + mn + "\n"
            # 找B1最集中的板块做深度搜索
            top_sectors = sorted(sector_b1, key=sector_b1.get, reverse=True)[:3]
            for s in top_sectors:
                sn = get_sector_news(s)
                if sn:
                    search_text += f"### {s}\n{sn}\n"
        except Exception as e:
            search_text = f"(搜索失败: {e})"

    # ==========================================
    # 3. LLM 整合
    # ==========================================
    prompt = f"""你是资深A股市场策略分析师。请基于以下数据生成今日市场环境报告。

日期：{date_str}

## 指数行情
{chr(10).join(f'- {q.get("name","?")}: {q.get("price","?")} ({q.get("change_pct",0):+.2f}%)' for q in quotes)}

## B1选股统计
B1活跃: {b1_count}只 | 近B1(J<20): {near_count}只 | 重点: {wl_l1}只 | 普通: {wl_l2}只
新进B1: {', '.join(new_b1[:15]) if new_b1 else '无'}

## 板块B1密度（前15）
{chr(10).join(f'- {k}: {v}只B1' for k,v in list(sector_b1.items())[:15])}

## Web搜索结果
{search_text or '(未搜索)'}

## 历史市场日记
{history[:1500] or '(无)'}

请输出Markdown格式的市场环境报告，结构如下：
### 大势研判
（指数表现+成交量+一句话判断）
### 主线板块
（B1密度最高的板块，判断是延续还是切换）
### 关注变化
（新进B1/消失B1/趋势状态转移）
### 风险提示
（科技拥挤度/地缘/季节性/其他）
### 明日关注
不构成投资建议。直接输出分析内容，不要加一级标题。"""

    llm_text = ""
    try:
        from llm.client import chat
        resp = chat([{"role":"system","content":"你是资深A股市场策略分析师"},{"role":"user","content":prompt}], max_tokens=4096)
        if resp:
            llm_text = resp["content"]
    except Exception:
        pass

    # ==========================================
    # 4. 存储
    # ==========================================
    report = f"""# 市场环境报告 — {date_str}

## 一、指数行情

| 指数 | 收盘 | 涨跌 |
|------|------|------|
{chr(10).join(f'| {q.get("name","?")} | {q.get("price","?")} | {q.get("change_pct",0):+.2f}% |' for q in quotes)}

## 二、B1统计

- ★ B1活跃: {b1_count}只
- △ 近B1(J<20): {near_count}只
- 重点关注: {wl_l1}只 | 普通关注: {wl_l2}只

## 三、板块B1密度

| 板块 | B1数 |
|------|------|
{chr(10).join(f'| {k} | {v} |' for k,v in list(sector_b1.items())[:15])}

## 四、WebSearch

{search_text or '(未搜索)'}

## 五、LLM解读

{llm_text or '(LLM未配置)'}

---

> 数据源: 掘金MyQuant/腾讯/baostock/Tavily | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""
    # 保存
    daily_path = os.path.join(base_dir, f"{date_str}.md")
    current_path = os.path.join(base_dir, "current.md")
    with open(daily_path, 'w', encoding='utf-8') as f:
        f.write(report)
    with open(current_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(report)

    # ==========================================
    # 5. 飞书
    # ==========================================
    if not args.output:  # output flag is reused as --no-publish equivalent
        try:
            # 发飞书消息
            import subprocess as sp
            msg = f"""市场环境报告({date_str})
指数涨跌 + B1统计{b1_count}只 + 板块排名 + WebSearch + LLM解读
完整报告: {daily_path}"""
            sp.run(["lark-cli", "im", "+messages-send", "--as", "bot",
                    "--user-id", "ou_d55b9054133a1e411d6c074e2f6eb11c",
                    "--markdown", msg], timeout=10)
        except Exception:
            pass


def _cmd_data_sync(args):
    """纯数据拉取，不计B1，不关注列表"""
    target = args.target

    if target == "calendar":
        from storage.db import get_db
        db = get_db()
        n = db.ensure_trading_calendar()
        days = db.get_trading_days("2026-01-01", "2027-01-01")
        print(f"交易日历: {len(days)}天, 最新={days[-1]}")
        return

    if target == "index":
        from data_source.quote_fetcher import QuoteFetcher, TRACKED_INDEXES
        from storage.db import get_db
        import time, random
        db = get_db()
        qf = QuoteFetcher()
        quotes = qf.get_index_quotes()
        today = db.conn.execute("SELECT MAX(date) FROM trading_calendar").fetchone()[0]
        print("指数行情:")
        for q in quotes:
            chg = q.get("change_pct", 0) or 0
            print(f"  {q['name']}({q['code']}): {q.get('price','?')} ({chg:+.2f}%) [{q.get('source','?')}]")
            # 写入 index_daily
            if q.get("price", 0) > 0:
                db.conn.execute(
                    "INSERT OR REPLACE INTO index_daily(code,date,close,change_pct,source) VALUES(?,?,?,?,?)",
                    (q["code"], today, q["price"], q["change_pct"], q.get("source", ""))
                )
        db.conn.commit()
        cnt = db.conn.execute("SELECT COUNT(*) FROM index_daily WHERE date=?", (today,)).fetchone()[0]
        print(f"  index_daily 写入: {cnt}条")
        return

    # target == "kline"
    from storage.kline_filler import ensure_candles

    codes = []
    if args.code:
        codes = [args.code]
    elif args.market:
        from config.blacklist import blacklist as bl
        print(f"[Data Sync] 全市场K线（不定时指标，不算B1）...")
        print(f"  {bl.summary()}")
        all_codes, name_map = _get_all_stock_codes()
        codes = [c for c in all_codes if not bl.is_banned(c, name_map.get(c, ""))]
        print(f"  {len(codes)} 只")
    elif args.all:
        from storage.db import get_db as _db2
        db2 = _db2()
        codes = [r[0] for r in db2.conn.execute("SELECT DISTINCT code FROM stock_daily").fetchall()]
        print(f"[Data Sync] 全部已有: {len(codes)} 只")
    else:
        print("请指定 --code / --market / --all")
        return

    ok = fail = 0
    for i, code in enumerate(codes):
        if i % 100 == 0:
            print(f"  [{i+1}/{len(codes)}] ok={ok} fail={fail}")
        candles = ensure_candles(code, required_days=args.days)
        if candles and len(candles) >= args.days:
            ok += 1
        else:
            fail += 1
    print(f"\n完成: ok={ok} fail={fail}")


def main():
    parser = argparse.ArgumentParser(prog="zhi-xing", description="知行股票分析系统 CLI")
    sub = parser.add_subparsers(dest="command", help="子命令")

    # indicator
    p_ind = sub.add_parser("indicator", help="计算知行指标")
    p_ind.add_argument("--symbol", "-s", help="股票代码")
    p_ind.add_argument("--input", "-i", help="K线JSON文件路径")

    # suo-bao
    p_sb = sub.add_parser("suo-bao", help="缩爆B1扫描")
    p_sb.add_argument("--symbol", "-s", help="股票代码")
    p_sb.add_argument("--input", "-i", help="K线JSON文件路径")
    p_sb.add_argument("--D", type=int, default=5)
    p_sb.add_argument("--S", type=float, default=0.75)
    p_sb.add_argument("--V", type=float, default=3)
    p_sb.add_argument("--N", type=float, default=0.2)

    # scan-sector-overview (板块概览，不扫个股)
    p_overview = sub.add_parser("scan-sector-overview", help="板块概览（走势/资金/龙头/异动，不扫个股）")
    p_overview.add_argument("--name", "-n", required=True, help="板块查询（如：电池、锂电专用设备）")
    p_overview.add_argument("--output", "-o", help="报告输出路径")
    p_overview.add_argument("--publish", action="store_true", default=True, help="发布到飞书（默认开启）")
    p_overview.add_argument("--no-publish", dest="publish", action="store_false", help="跳过飞书发布")

    # scan-sector-b1 (个股B1扫描)
    p_b1 = sub.add_parser("scan-sector-b1", help="板块B1扫描（逐只K线+知行指标）")
    p_b1.add_argument("--name", "-n", required=True, help="板块查询（如：电池、锂电池概念）")
    p_b1.add_argument("--output", "-o", help="报告输出路径")
    p_b1.add_argument("--workers", type=int, default=20, help="并行线程数")
    p_b1.add_argument("--days", type=int, default=120, help="K线天数（B1需要114天）")
    p_b1.add_argument("--no-cache", action="store_true", help="禁用缓存")
    p_b1.add_argument("--no-auto-save", action="store_true", help="禁止自动入库到关注列表")
    p_b1.add_argument("--publish", action="store_true", default=True, help="发布到飞书（默认开启）")
    p_b1.add_argument("--no-publish", dest="publish", action="store_false", help="跳过飞书发布")

    # scan-market (stub)
    p_mkt = sub.add_parser("scan-market", help="全市场扫描（以板块为单元循环）")
    p_mkt.add_argument("--output", "-o", help="报告输出路径")
    p_mkt.add_argument("--workers", type=int, default=20)
    p_mkt.add_argument("--days", type=int, default=120)
    p_mkt.add_argument("--no-cache", action="store_true")
    p_mkt.add_argument("--max-sectors", type=int, default=0, help="最多扫描板块数（0=全部）")

    # report (from raw JSON)
    p_rpt = sub.add_parser("report", help="从原始JSON生成报告")
    p_rpt.add_argument("--input", "-i", required=True, help="原始JSON文件路径")
    p_rpt.add_argument("--output", "-o", help="报告输出路径")

    # publish
    p_pub = sub.add_parser("publish", help="发布报告到飞书")
    p_pub.add_argument("--input", "-i", required=True, help="MD报告文件路径")
    p_pub.add_argument("--title", help="文档标题")
    p_pub.add_argument("--folder", help="飞书文件夹token")

    # === Phase C: 持仓管理 ===
    p_ha = sub.add_parser("holdings-add", help="新增或更新持仓")
    p_ha.add_argument("--code", "-c", required=True, help="股票代码")
    p_ha.add_argument("--name", "-n", help="股票名称")
    p_ha.add_argument("--cost", type=float, required=True, help="成本价")
    p_ha.add_argument("--qty", type=int, required=True, help="持仓数量")
    p_ha.add_argument("--strategy", help="策略标签")
    p_ha.add_argument("--notes", help="备注")
    p_ha.add_argument("--stop-loss", type=float, help="止损价")
    p_ha.add_argument("--target", type=float, help="目标价")

    p_hl = sub.add_parser("holdings-list", help="列出当前持仓")
    p_hl.add_argument("--verbose", "-v", action="store_true", help="显示详细信息")

    p_ta = sub.add_parser("transaction-add", help="新增交易流水")
    p_ta.add_argument("--code", "-c", required=True, help="股票代码")
    p_ta.add_argument("--date", default=_now_short(), help="交易日期 (YYYY-MM-DD)")
    p_ta.add_argument("--direction", required=True, choices=["buy","sell","t_buy","t_sell","clear"], help="买卖方向")
    p_ta.add_argument("--qty", type=int, required=True, help="数量")
    p_ta.add_argument("--price", type=float, required=True, help="成交价")
    p_ta.add_argument("--reason", help="交易理由")
    p_ta.add_argument("--memo", help="备注")

    p_tl = sub.add_parser("transaction-list", help="查看交易流水")
    p_tl.add_argument("--code", "-c", help="股票代码（不指定=全部）")
    p_tl.add_argument("--days", type=int, default=90, help="查询天数")
    p_tl.add_argument("--limit", type=int, default=100, help="最大条数")

    # === Phase C: 关注列表 ===
    p_wa = sub.add_parser("watchlist-add", help="加入关注列表")
    p_wa.add_argument("--code", "-c", required=True, help="股票代码")
    p_wa.add_argument("--name", "-n", help="股票名称")
    p_wa.add_argument("--reason", "-r", help="关注原因")
    p_wa.add_argument("--priority", type=int, default=3, help="优先级 1-5")
    p_wa.add_argument("--tags", help="标签JSON，如 '[\"锂电池\",\"B1\"]'")
    p_wa.add_argument("--price", type=float, help="添加时价格")
    p_wa.add_argument("--notes", help="备注")

    p_wl = sub.add_parser("watchlist-list", help="查看关注列表")
    p_wl.add_argument("--status", default="active", help="状态筛选: active/observing/archived/all")

    p_wr = sub.add_parser("watchlist-remove", help="移出关注列表")
    p_wr.add_argument("--code", "-c", required=True, help="股票代码")
    p_wr.add_argument("--reason", "-r", default="手动移出", help="移出原因")

    p_wp = sub.add_parser("watchlist-promote", help="升级为重点关注(level=1)")
    p_wp.add_argument("--code", "-c", required=True, help="股票代码")

    p_wd = sub.add_parser("watchlist-demote", help="降级为普通关注(level=2)")
    p_wd.add_argument("--code", "-c", required=True, help="股票代码")

    # === Phase C: 日终追踪 + B1追踪 ===
    p_dr = sub.add_parser("daily-review", help="日终追踪（拉K线+算指标+状态转换+预警）")
    p_dr.add_argument("--date", help="日期 (YYYY-MM-DD)")
    p_dr.add_argument("--sector", help="额外扫描板块，逗号分隔")
    p_dr.add_argument("--workers", type=int, default=10, help="并行线程数")
    p_dr.add_argument("--output", "-o", help="JSON摘要输出路径")

    p_bt = sub.add_parser("b1-tracking", help="查看B1状态追踪历史")
    p_bt.add_argument("--code", "-c", required=True, help="股票代码")
    p_bt.add_argument("--limit", type=int, default=30, help="显示条数")

    # === Phase C: 重点板块 ===
    p_fa = sub.add_parser("focus-sector-add", help="添加重点板块")
    p_fa.add_argument("--name", "-n", required=True, help="板块名称")
    p_fa.add_argument("--type", default="industry", choices=["industry","concept"], help="板块类型")
    p_fa.add_argument("--source", default="manual", help="来源")
    p_fa.add_argument("--priority", type=int, default=3, help="优先级")
    p_fa.add_argument("--notes", help="备注")
    p_fa.add_argument("--tags", help="标签JSON")

    p_fl = sub.add_parser("focus-sector-list", help="查看重点板块")
    p_fl.add_argument("--status", default="active", help="状态筛选")

    # === Phase F: LLM 报告解析 ===
    p_ls = sub.add_parser("llm-stock", help="个股AI技术解读（LLM增强，可选--sector 触发板块横向对比）")
    p_ls.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_ls.add_argument("--days", type=int, default=114, help="K线天数")
    p_ls.add_argument("--sector", help="所属板块名（指定后触发三层深度分析：个股+板块定位+大局研判）")

    p_ln = sub.add_parser("llm-sector", help="板块扫描 + AI叙事增强")
    p_ln.add_argument("--name", "-n", required=True, help="板块名")
    p_ln.add_argument("--workers", type=int, default=20)
    p_ln.add_argument("--days", type=int, default=120)

    p_hl = sub.add_parser("holdings-letter", help="生成持仓日报（分析师口吻+次日建议）")
    p_hl.add_argument("--output", "-o", help="报告输出路径")

    p_hr = sub.add_parser("holdings-review", help="持仓复盘/监控（LLM分析今日操作得失或当前持仓状态）")
    p_hr.add_argument("--date", default=_now_short(), help="日期 (YYYY-MM-DD)，默认今天")
    p_hr.add_argument("--mode", choices=["auto", "review", "monitor"], default="auto",
                      help="auto=今天自动复盘，其他日期自动监控; review=强制复盘; monitor=强制监控")
    p_hr.add_argument("--output", "-o", help="报告输出路径")

    p_wr_llm = sub.add_parser("watchlist-report", help="生成关注列表监控报告")
    p_wr_llm.add_argument("--output", "-o", help="报告输出路径")

    p_td = sub.add_parser("trade-diagnosis", help="交易前AI诊断")
    p_td.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_td.add_argument("--name", help="股票名称")
    p_td.add_argument("--action", required=True, choices=["buy", "sell"], help="操作方向")
    p_td.add_argument("--shares", type=int, required=True, help="计划数量")
    p_td.add_argument("--days", type=int, default=114, help="K线天数")

    # === 账户管理 ===
    p_as = sub.add_parser("account-update", help="更新账户快照（总资产/可用资金/仓位）")
    p_as.add_argument("--total", type=float, required=True, help="总资产")
    p_as.add_argument("--cash", type=float, required=True, help="可用资金")
    p_as.add_argument("--position-ratio", type=float, help="仓位(百分比)")
    p_as.add_argument("--pnl", type=float, help="总持仓盈亏")

    # === 行业分类索引 ===
    p_irb = sub.add_parser("industry-rebuild", help="重建行业分类索引（同花顺/东方财富）")
    p_irb.add_argument("--source", "-s", required=True, choices=["ths", "em"],
                        help="ths=同花顺(iFind) / em=东方财富(akshare)")
    p_il = sub.add_parser("industry-lookup", help="查询行业标签（个股→行业 / 行业→成分股）")
    p_il.add_argument("--code", "-c", help="股票代码（查该股行业标签）")
    p_il.add_argument("--name", "-n", help="行业名（查该行业成分股）")
    p_il.add_argument("--source", choices=["ths", "em"], default="ths", help="分类体系")
    p_il.add_argument("--search", help="模糊搜索行业名")

    # === 行业研究 ===
    p_ir = sub.add_parser("industry-research", help="读取URL/文本/stdin → LLM总结行业逻辑 → 保存到 references/")
    p_ir.add_argument("--topic", "-t", required=True, help="行业/主题名（如 PCB、机器人）")
    p_ir.add_argument("--urls", "-u", nargs="*", help="参考URL列表")
    p_ir.add_argument("--text", help="直接输入文本分析")
    p_ir.add_argument("--stdin", action="store_true", help="从stdin读取（OpenClaw搜索结果pipe进来）")
    p_ir.add_argument("--output", "-o", help="输出路径（默认 references/industry_logic/{topic}_行业逻辑.md）")

    # === K线综合分析 ===
    p_ka = sub.add_parser("kline-analyze", help="K线形态+基本面+题材+B1 综合分析（LLM）")
    p_ka.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_ka.add_argument("--name", help="股票名称")
    p_ka.add_argument("--theme", help="题材/产业链名")
    p_ka.add_argument("--days", type=int, default=114, help="K线天数")
    p_ka.add_argument("--verify", action="store_true", help="双源交叉验证K线数据")
    p_ka.add_argument("--output", "-o", help="报告输出路径")

    # === Phase G: 数据报告 ===
    p_dr = sub.add_parser("data-report", help="个股完整数据报告（B1+基本面+估值+消息+板块+市场）")
    p_dr.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_dr.add_argument("--name", help="股票名称")
    p_dr.add_argument("--sector", help="所属板块名（传统板块扫描）")
    p_dr.add_argument("--theme", help="主题/产业链名（如 机器人/算力/低空经济，精确对标产业链核心标的）")
    p_dr.add_argument("--output", "-o", help="报告输出路径")
    p_dr.add_argument("--days", type=int, default=114, help="K线天数")

    p_sr = sub.add_parser("sector-report", help="板块扫描数据报告（龙头+B1+领涨+基本面）")
    p_sr.add_argument("--name", "-n", required=True, help="板块名")
    p_sr.add_argument("--output", "-o", help="报告输出路径")
    p_sr.add_argument("--workers", type=int, default=20)
    p_sr.add_argument("--days", type=int, default=120)

    # === 数据管理 ===
    p_ku = sub.add_parser("kline-update", help="更新K线数据到数据库")
    p_ku.add_argument("--code", "-c", help="股票代码（单只）")
    p_ku.add_argument("--all", action="store_true", help="更新全部已有股票")
    p_ku.add_argument("--market", action="store_true", help="全市场扫描（排除920/688）")
    p_ku.add_argument("--add-watchlist", action="store_true", help="B1候选自动入库关注列表")
    p_ku.add_argument("--sector", "-s", help="板块名，更新该板块所有成分股")
    p_ku.add_argument("--days", type=int, default=114, help="需要多少交易日数据")

    p_su = sub.add_parser("sector-update", help="更新东财板块成分股缓存")
    p_su.add_argument("--name", "-n", help="板块名（不指定则使用theme_chains全量）")
    p_su.add_argument("--type", default="concept", choices=["concept","industry"])
    p_su.add_argument("--all", action="store_true", help="全量更新（theme_chains.py 所有板块）")

    # === 实时行情 ===
    p_q = sub.add_parser("quote", help="实时行情查询（掘金→腾讯→akshare级联）")
    p_q.add_argument("--symbol", "-s", help="股票代码（单只）")
    p_q.add_argument("--holdings", action="store_true", help="当前持仓行情")
    p_q.add_argument("--watch", action="store_true", help="关注列表行情")
    p_q.add_argument("--index", action="store_true", help="主要指数行情")

    # === 知行趋势指标 ===
    p_trend = sub.add_parser("trend", help="知行趋势分析（黄白线独立指标）")
    p_trend.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_trend.add_argument("--days", type=int, default=125, help="K线天数")

    # === 日更（含趋势） ===
    p_du = sub.add_parser("daily-update", help="日更全流程（K线+B1+趋势+关注列表分层）")
    p_du.add_argument("--days", type=int, default=125, help="需要多少交易日数据")

    # === scan — 选股引擎 ===
    p_scan = sub.add_parser("scan", help="选股引擎（B1+缩量爆发，数据不足自动补）")
    p_scan.add_argument("--name", "-n", help="板块名（theme_chains映射）")
    p_scan.add_argument("--market", action="store_true", help="全市场扫描")
    p_scan.add_argument("--codes", help="指定代码列表（逗号分隔）")
    p_scan.add_argument("--days", type=int, default=114, help="需要多少交易日")
    p_scan.add_argument("--auto-save", action="store_true", help="B1→重点关注, 近B1→普通关注")
    p_scan.add_argument("--ai", action="store_true", help="LLM板块叙事增强（需ZX_LLM_API_KEY）")

    # === market report ===
    p_mr = sub.add_parser("market-report", help="市场环境报告（指数+板块+主线+WebSearch→LLM）")
    p_mr.add_argument("--theme", help="主线专题深度分析")
    p_mr.add_argument("--no-search", action="store_true", help="不用Web Search")
    p_mr.add_argument("--output", "-o", help="输出路径")

    # === find — 智能选股 ===
    p_find = sub.add_parser("find", help="智能选股（板块→扫描→B1+趋势，支持模糊语义）")
    p_find.add_argument("query", nargs="?", help="自然语言 query 或精确板块名")
    p_find.add_argument("--name", "-n", help="精确板块名（不走LLM）")

    # === data sync — 纯数据拉取（定时任务，不算B1） ===
    p_data = sub.add_parser("data", help="数据管理")
    p_data_subs = p_data.add_subparsers(dest="data_cmd", help="子命令")

    p_ds = p_data_subs.add_parser("sync", help="同步数据到数据库")
    p_ds.add_argument("--target", required=True, choices=["kline", "index", "calendar"],
                      help="kline=K线 | index=指数 | calendar=交易日历")
    p_ds.add_argument("--code", "-c", help="股票代码（单只）")
    p_ds.add_argument("--market", action="store_true", help="全市场")
    p_ds.add_argument("--all", action="store_true", help="全部已有股票")
    p_ds.add_argument("--days", type=int, default=114, help="需要多少交易日数据")

    args = parser.parse_args()

    if args.command == "list-sectors":
        from data_source.sector_registry import list_known_concepts, get_concept_alias_map
        print("=== 已知概念板块 ===")
        for c in list_known_concepts():
            print(f"  {c}")
        print(f"\n=== 别名映射 ===")
        for alias, concept in sorted(get_concept_alias_map().items()):
            print(f"  {alias} → {concept}")
    elif args.command == "indicator":
        cmd_indicator(args)
    elif args.command == "suo-bao":
        cmd_suo_bao(args)
    elif args.command == "scan-sector-overview":
        cmd_scan_overview(args)
    elif args.command == "scan-sector-b1":
        cmd_scan_b1(args)
    elif args.command == "scan-market":
        cmd_scan_market(args)
    elif args.command == "report":
        cmd_report(args)
    elif args.command == "publish":
        cmd_publish(args)

    # === Phase C: 持仓管理 ===
    elif args.command == "holdings-add":
        cmd_holdings_add(args)
    elif args.command == "holdings-list":
        cmd_holdings_list(args)
    elif args.command == "transaction-add":
        cmd_transaction_add(args)
    elif args.command == "transaction-list":
        cmd_transaction_list(args)

    # === Phase C: 关注列表 ===
    elif args.command == "watchlist-add":
        cmd_watchlist_add(args)
    elif args.command == "watchlist-list":
        cmd_watchlist_list(args)
    elif args.command == "watchlist-remove":
        cmd_watchlist_remove(args)
    elif args.command == "watchlist-promote":
        from storage.portfolio_db import set_watchlist_level
        ok = set_watchlist_level(args.code, 1)
        print(f"{'升级成功' if ok else '未找到'}: {args.code} 重点")
    elif args.command == "watchlist-demote":
        from storage.portfolio_db import set_watchlist_level
        ok = set_watchlist_level(args.code, 2)
        print(f"{'降级成功' if ok else '未找到'}: {args.code} 普通")

    # === Phase C: 日终追踪 + B1追踪 ===
    elif args.command == "daily-review":
        cmd_daily_review(args)
    elif args.command == "b1-tracking":
        cmd_b1_tracking(args)

    # === Phase C: 重点板块 ===
    elif args.command == "focus-sector-add":
        cmd_focus_sector_add(args)
    elif args.command == "focus-sector-list":
        cmd_focus_sector_list(args)

    # === Phase F: LLM 报告解析 ===
    elif args.command == "llm-stock":
        cmd_llm_stock(args)
    elif args.command == "llm-sector":
        cmd_llm_sector(args)
    elif args.command == "holdings-letter":
        cmd_holdings_letter(args)
    elif args.command == "holdings-review":
        cmd_holdings_review(args)
    elif args.command == "watchlist-report":
        cmd_watchlist_report(args)
    elif args.command == "trade-diagnosis":
        cmd_trade_diagnosis(args)

    # === 账户管理 ===
    elif args.command == "account-update":
        cmd_account_update(args)

    # === 行业分类索引 ===
    elif args.command == "industry-rebuild":
        cmd_industry_rebuild(args)
    elif args.command == "industry-lookup":
        cmd_industry_lookup(args)

    # === 行业研究 ===
    elif args.command == "industry-research":
        cmd_industry_research(args)

    # === K线综合分析 ===
    elif args.command == "kline-analyze":
        cmd_kline_analyze(args)

    # === Phase G: 数据报告 ===
    elif args.command == "data-report":
        cmd_data_report(args)
    elif args.command == "sector-report":
        cmd_sector_report(args)

    # === 数据管理 ===
    elif args.command == "kline-update":
        cmd_kline_update(args)
    elif args.command == "sector-update":
        cmd_sector_update(args)

    # === 实时行情 ===
    elif args.command == "quote":
        cmd_quote(args)

    # === 知行趋势 ===
    elif args.command == "trend":
        cmd_trend(args)

    # === 日更全流程 ===
    elif args.command == "daily-update":
        cmd_daily_update(args)

    # === 选股引擎 ===
    elif args.command == "scan":
        cmd_scan(args)

    # === 市场环境报告 ===
    elif args.command == "market-report":
        cmd_market_report(args)

    # === find 智能选股 ===
    elif args.command == "find":
        cmd_find(args)

    # === data 数据管理 ===
    elif args.command == "data":
        cmd_data(args)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
