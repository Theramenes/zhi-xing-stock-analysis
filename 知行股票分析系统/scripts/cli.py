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

    p_wr_llm = sub.add_parser("watchlist-report", help="生成关注列表监控报告")
    p_wr_llm.add_argument("--output", "-o", help="报告输出路径")

    p_td = sub.add_parser("trade-diagnosis", help="交易前AI诊断")
    p_td.add_argument("--symbol", "-s", required=True, help="股票代码")
    p_td.add_argument("--name", help="股票名称")
    p_td.add_argument("--action", required=True, choices=["buy", "sell"], help="操作方向")
    p_td.add_argument("--shares", type=int, required=True, help="计划数量")
    p_td.add_argument("--days", type=int, default=114, help="K线天数")

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
    elif args.command == "watchlist-report":
        cmd_watchlist_report(args)
    elif args.command == "trade-diagnosis":
        cmd_trade_diagnosis(args)

    # === Phase G: 数据报告 ===
    elif args.command == "data-report":
        cmd_data_report(args)
    elif args.command == "sector-report":
        cmd_sector_report(args)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
