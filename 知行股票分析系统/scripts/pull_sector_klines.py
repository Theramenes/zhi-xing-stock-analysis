"""
批量拉取某板块成分股的 K 线到本地 SQLite。
逻辑: 有 >=114 天则跳过，缺则补，无则全拉。
用法: python scripts/pull_sector_klines.py --sector 印制电路板
策略: snapshot 逐日优先（多线程）→ 缺的部分 date_sequence 批量兜底。
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from data_source.registry import registry as ds_registry
from data_source.base import StockInfo
from storage.db import get_db


def get_sector_members(sector_name: str) -> list:
    """获取板块成分股"""
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        print("iFind 不可用，无法获取板块成分股")
        return []

    searchstring = f"{sector_name}行业"
    members = ifind.get_sector_members(searchstring)
    if not members:
        import json
        payload = json.dumps(
            {"searchstring": f"{searchstring} 成分股 股票代码 股票简称", "searchtype": "stock"},
            ensure_ascii=False,
        )
        data = ifind._call(
            "endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=60
        )
        if data and data.get("ok"):
            tables = data.get("data", {}).get("tables", [])
            if tables:
                tb = tables[0].get("table", {})
                codes = tb.get("股票代码", [])
                names = tb.get("股票简称", [])
                members = [
                    StockInfo(code=str(codes[i]).split(".")[0], name=str(names[i]))
                    for i in range(min(len(codes), len(names)))
                ]
    return members


def main():
    parser = argparse.ArgumentParser(description="板块 K 线批量入库")
    parser.add_argument("--sector", required=True, help="板块名，如 印制电路板")
    parser.add_argument("--days", type=int, default=114, help="最少需要多少交易日（默认114）")
    parser.add_argument("--delay", type=float, default=0.3, help="每只请求间隔秒数（默认0.3）")
    args = parser.parse_args()

    db = get_db()
    print(f"[DB] 当前库: {db.stock_count} 只股票, {db.total_rows} 条记录")

    print(f"[Sector] 获取 '{args.sector}' 成分股...")
    members = get_sector_members(args.sector)
    if not members:
        print("无成分股，退出")
        return

    print(f"  共 {len(members)} 只")

    skipped = []
    filled = []
    errors = []

    for i, m in enumerate(members, 1):
        stats = db.stock_stats(m.code)
        existing_days = stats["days"] or 0

        if existing_days >= args.days:
            skipped.append((m.code, m.name, existing_days))
            print(f"  [{i}/{len(members)}] {m.code} {m.name}: 已有 {existing_days} 天，跳过")
            continue

        print(f"  [{i}/{len(members)}] {m.code} {m.name}: 现有 {existing_days} 天，开始补缺...")
        try:
            # snapshot 优先（多线程）→ 缺的 date_sequence 兜底，严格不超 114 天
            from storage.kline_filler import ensure_candles
            candles = ensure_candles(m.code, required_days=args.days)
            new_days = len(candles)
            filled.append((m.code, m.name, existing_days, new_days))
            print(f"    -> 现在共 {new_days} 天")
        except Exception as e:
            errors.append((m.code, m.name, str(e)))
            print(f"    -> 异常: {e}")

        time.sleep(args.delay)

    print("\n" + "=" * 50)
    print("汇总")
    print(f"  成分股总数: {len(members)}")
    print(f"  已满足跳过: {len(skipped)} 只")
    print(f"  补充/填充 : {len(filled)} 只")
    print(f"  失败      : {len(errors)} 只")

    if filled:
        print("\n  补充明细:")
        for code, name, old, new in filled[:10]:
            print(f"    {code} {name}: {old} -> {new} 天")
        if len(filled) > 10:
            print(f"    ... 等共 {len(filled)} 只")

    if errors:
        print("\n  失败明细:")
        for code, name, err in errors[:5]:
            print(f"    {code} {name}: {err}")

    print(f"\n[DB] 结束: {db.stock_count} 只股票, {db.total_rows} 条记录")


if __name__ == "__main__":
    main()
