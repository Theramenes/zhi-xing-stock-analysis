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
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
