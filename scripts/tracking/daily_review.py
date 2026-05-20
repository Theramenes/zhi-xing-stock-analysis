# -*- coding: utf-8 -*-
"""
日终追踪流程编排。

流程：
1. 拉取所有 watchlist active/observing + position 持仓票的最新K线
2. 跑 b1_calculator 算指标
3. 存入 watchlist_daily / position_snapshot
4. 跑状态机 transition，更新 b1_tracking
5. 检测变化，生成预警列表
6. 自动将 B1 票写入 watchlist + b1_candidate（排重）
7. 清理过期观察票（7天）
8. 返回结构化变化摘要
"""
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.portfolio_db import (
    list_positions, add_position, snapshot_position,
    add_to_watchlist, list_watchlist, record_watchlist_daily,
    record_b1_scan, add_b1_candidate,
    update_b1_stage, get_b1_tracking, get_expired_observing,
    update_watchlist_status, detect_watchlist_changes,
)
from tracking.state_machine import transition, generate_alerts
from indicators.b1_calculator import compute_single
from storage.kline_filler import ensure_candles


def _now():
    return datetime.now().strftime("%Y-%m-%d")


def _to_candles(kline_rows: list) -> list:
    """把 db.get_candles 返回的 dict 列表转 compute_single 需要的 candles 格式"""
    return [
        {"date": r["date"], "open": r["open"], "high": r["high"],
         "low": r["low"], "close": r["close"], "volume": r["volume"]}
        for r in kline_rows
    ]


def fetch_and_compute(code: str):
    """拉取K线并计算指标。返回 (code, indicators_dict, error)"""
    try:
        from storage.db import get_db
        db = get_db()
        # 确保至少有 120 根K线
        candles = ensure_candles(code, required_days=120)
        if not candles or len(candles) < 114:
            return (code, None, f"K线不足 {len(candles) if candles else 0} 天")

        result = compute_single(code, candles)
        if "error" in result:
            return (code, None, result["error"])

        return (code, result, None)
    except Exception as e:
        return (code, None, str(e))


def run_daily_review(sectors_to_scan: list = None, workers: int = 10) -> dict:
    """
    日终追踪入口。
    sectors_to_scan: [(sector_name, sector_type), ...] 额外要扫描的板块
    """
    today = _now()
    summary = {
        "date": today,
        "watchlist_scanned": 0,
        "positions_snapshotted": 0,
        "new_b1": [],
        "b1_lost": [],
        "near_b1": [],
        "stage_changes": [],
        "expired_cleaned": [],
        "alerts": [],
        "errors": [],
    }

    # ---- 1. 收集需要拉K线的股票 ----
    codes_to_scan = set()

    wl_items = list_watchlist("active") + list_watchlist("observing")
    for w in wl_items:
        codes_to_scan.add(w["code"])

    positions = list_positions()
    pos_codes = set()
    for p in positions:
        codes_to_scan.add(p["code"])
        pos_codes.add(p["code"])

    if not codes_to_scan:
        summary["errors"].append("无关注票、无持仓，无需扫描")
        return summary

    # ---- 2. 并行拉K线 + 算指标 ----
    results = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_and_compute, c): c for c in codes_to_scan}
        for f in as_completed(futures):
            code, indicators, err = f.result()
            if err:
                summary["errors"].append(f"{code}: {err}")
            else:
                results[code] = indicators

    # ---- 3. 存快照 + 状态转换 ----
    for w in wl_items:
        code = w["code"]
        if code not in results:
            continue
        ind = results[code]
        record_watchlist_daily(code, ind)

        # 状态转换
        from tracking.state_machine import apply_transition
        change = apply_transition(code, ind)
        if change["from"] != change["to"]:
            summary["stage_changes"].append(change)

        # 分类
        sigs = ind.get("信号", [])
        if sigs:
            if change["to"] == "b1":
                summary["new_b1"].append({
                    "code": code, "name": w.get("name", ""),
                    "signals": sigs, "J": ind.get("J"),
                    "score": ind.get("评分"), "trend": ind.get("趋势"),
                })
        else:
            if change["from"] in ("b1", "near_b1", "observing"):
                summary["b1_lost"].append({
                    "code": code, "name": w.get("name", ""),
                    "J": ind.get("J"), "from_stage": change["from"],
                })
            if ind.get("J", 999) < 20:
                if change["to"] not in ("b1",):
                    summary["near_b1"].append({
                        "code": code, "name": w.get("name", ""),
                        "J": ind.get("J"), "score": ind.get("评分"),
                    })

    summary["watchlist_scanned"] = len(wl_items)

    # ---- 4. 持仓快照 ----
    for p in positions:
        code = p["code"]
        if code not in results:
            continue
        ind = results[code]
        snapshot_position(
            code, p.get("name", ""), p.get("total_qty", 0),
            p.get("avg_cost", 0), ind.get("last", 0), ind,
        )
        # 追踪持仓票的 B1 状态
        current = get_b1_tracking(code, limit=1)
        stage = current[-1]["stage"] if current else "watching"
        next_stage = transition(stage, ind)
        if next_stage != stage:
            update_b1_stage(code, next_stage, ind, f"{stage} → {next_stage}")
            summary["stage_changes"].append({
                "code": code, "from": stage, "to": next_stage,
                "memo": f"{stage} → {next_stage}",
            })
    summary["positions_snapshotted"] = len(positions)

    # ---- 5. 额外板块扫描（如果有）----
    if sectors_to_scan:
        _do_sector_scan(sectors_to_scan, summary, workers)

    # ---- 6. 清理过期观察票 ----
    expired = get_expired_observing(days=7)
    for code in expired:
        update_watchlist_status(code, "archived", "7天观察期满未恢复B1")
        update_b1_stage(code, "archived", {}, "观察期满自动归档")
        summary["expired_cleaned"].append(code)

    # ---- 7. 生成预警 ----
    summary["alerts"] = generate_alerts(positions, wl_items)

    return summary


def _do_sector_scan(sectors, summary, workers=10):
    """对指定板块做 B1 扫描，结果自动入库"""
    from scanning.sector_scanner import SectorB1Scanner

    all_b1 = []
    for sector_name, sector_type in sectors:
        try:
            scanner = SectorB1Scanner(workers=workers, use_cache=True)
            combined = scanner.scan(sector_name)
            b1 = combined.get("b1")
            if not b1:
                continue

            scan_id = record_b1_scan(
                "sector", sector_name,
                total=len(b1.stocks) if b1.stocks else 0,
                b1=len(b1.b1_stocks) if b1.b1_stocks else 0,
                near=len(b1.near_b1_stocks) if b1.near_b1_stocks else 0,
            )

            for s in (b1.b1_stocks or []):
                d = s.to_dict() if hasattr(s, "to_dict") else s.__dict__
                all_b1.append(d)
                add_b1_candidate(scan_id, d.get("code", ""), d.get("name", ""),
                                 sector_name, "B1", d)
                add_to_watchlist(d.get("code", ""), d.get("name", ""),
                                 source="auto_scan", reason=f"{sector_name} B1",
                                 tags=[sector_name])
                record_watchlist_daily(d.get("code", ""), d)

            for s in (b1.near_b1_stocks or []):
                d = s.to_dict() if hasattr(s, "to_dict") else s.__dict__
                add_b1_candidate(scan_id, d.get("code", ""), d.get("name", ""),
                                 sector_name, "near_B1", d)
                add_to_watchlist(d.get("code", ""), d.get("name", ""),
                                 source="auto_scan", reason=f"{sector_name} 近B1",
                                 tags=[sector_name])
                record_watchlist_daily(d.get("code", ""), d)
        except Exception as e:
            summary["errors"].append(f"板块{sector_name}扫描失败: {e}")

    # 去重后计入摘要
    seen = set()
    for d in all_b1:
        code = d.get("code", "")
        if code in seen:
            continue
        seen.add(code)
        s = summary.setdefault("new_b1", [])
        s.append({
            "code": code, "name": d.get("name", ""),
            "signals": d.get("signals", []), "J": d.get("J"),
            "score": d.get("score"), "trend": d.get("趋势"),
        })


def generate_summary_text(summary: dict) -> str:
    """将日终结果摘要格式化为终端文本"""
    lines = []
    L = lines.append
    L(f"=== 知行日终追踪 {summary['date']} ===")
    L(f"关注票: {summary['watchlist_scanned']}  持仓快照: {summary['positions_snapshotted']}")

    if summary.get("new_b1"):
        L(f"\n【新B1信号】{len(summary['new_b1'])}只")
        for b in summary["new_b1"][:10]:
            sigs = ", ".join(b.get("signals", [])[:3])
            L(f"  {b['code']} {b['name']} J={b.get('J','?')} 评分={b.get('score','?')} [{sigs}]")

    if summary.get("b1_lost"):
        L(f"\n【B1消失】{len(summary['b1_lost'])}只")
        for b in summary["b1_lost"][:5]:
            L(f"  {b['code']} {b['name']} J={b.get('J','?')} 来源={b.get('from_stage','?')} → observing")

    if summary.get("near_b1"):
        L(f"\n【近B1观察】{len(summary['near_b1'])}只 (J<20)")
        for b in summary["near_b1"][:5]:
            L(f"  {b['code']} {b['name']} J={b.get('J','?')} 评分={b.get('score','?')}")

    if summary.get("stage_changes"):
        L(f"\n【状态变更】{len(summary['stage_changes'])}条")
        for c in summary["stage_changes"][:10]:
            L(f"  {c['code']}: {c['from']} → {c['to']}")

    if summary.get("expired_cleaned"):
        L(f"\n【过期清理】{len(summary['expired_cleaned'])}只")
        for code in summary["expired_cleaned"][:5]:
            L(f"  {code} → archived（7天观察期满）")

    if summary.get("alerts"):
        L(f"\n【预警】{len(summary['alerts'])}条")
        for a in summary["alerts"]:
            L(f"  [{a['type']}] {a['code']} {a.get('name','')} {a.get('detail','')}")

    if summary.get("errors"):
        L(f"\n【错误】{len(summary['errors'])}条")
        for e in summary["errors"][:5]:
            L(f"  {e}")

    return "\n".join(lines)
