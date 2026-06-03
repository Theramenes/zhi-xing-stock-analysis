# -*- coding: utf-8 -*-
"""
业务数据访问层 — 持仓/关注/B1追踪/板块所有 CRUD 操作
复用 db.py 的 StockDB 连接，不单独管理连接。
"""
import json
import os
from datetime import datetime
from typing import Optional, List, Dict, Any

from .db import get_db

_db = None


def _ensure_db():
    global _db
    if _db is None:
        _db = get_db()
    return _db


# ============================================================
# 通用工具
# ============================================================

def _now():
    return datetime.now().strftime("%Y-%m-%d")

def _now_ts():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def _safe_json(v: Any) -> str:
    if v is None:
        return "[]"
    if isinstance(v, str):
        return v
    return json.dumps(v, ensure_ascii=False)


# ============================================================
# 持仓 Position
# ============================================================

def add_position(code: str, name: str = "", avg_cost: float = 0, total_qty: int = 0,
                 available_qty: int = None, strategy: str = "", notes: str = "",
                 stop_loss: float = None, target_price: float = None) -> int:
    """新增或更新持仓头寸。返回 1=新增, 2=更新, 0=失败。"""
    db = _ensure_db()
    if available_qty is None:
        available_qty = total_qty
    now = _now_ts()
    try:
        existing = db.conn.execute(
            "SELECT code FROM position WHERE code=?", (code,)
        ).fetchone()
        if existing:
            db.conn.execute(
                """UPDATE position SET name=?, avg_cost=?, total_qty=?, available_qty=?,
                   strategy=?, notes=?, stop_loss=?, target_price=?, last_trade_date=?,
                   updated_at=? WHERE code=?""",
                (name, avg_cost, total_qty, available_qty, strategy, notes,
                 stop_loss, target_price, _now(), now, code)
            )
            db.conn.commit()
            return 2
        else:
            db.conn.execute(
                """INSERT INTO position (code, name, avg_cost, total_qty, available_qty,
                   first_buy_date, last_trade_date, strategy, notes, stop_loss,
                   target_price, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (code, name, avg_cost, total_qty, available_qty,
                 _now(), _now(), strategy, notes, stop_loss, target_price, now)
            )
            db.conn.commit()
            return 1
    except Exception:
        return 0


def get_position(code: str) -> Optional[dict]:
    db = _ensure_db()
    row = db.conn.execute("SELECT * FROM position WHERE code=?", (code,)).fetchone()
    if not row:
        return None
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(position)").fetchall()]
    return dict(zip(cols, row))


def list_positions(status: str = None) -> List[dict]:
    db = _ensure_db()
    rows = db.conn.execute("SELECT * FROM position ORDER BY code").fetchall()
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(position)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def list_positions_with_archive(date: str = None, include_active: bool = True) -> List[dict]:
    """返回持仓视图：当前持仓 + 指定日期已归档的持仓。
    若 date 为空，返回所有（含历史归档）。
    每条记录会带上 status: 'active' | 'closed'。"""
    db = _ensure_db()
    results = []

    if include_active:
        rows = db.conn.execute("SELECT * FROM position ORDER BY code").fetchall()
        cols = [c[1] for c in db.conn.execute("PRAGMA table_info(position)").fetchall()]
        for r in rows:
            d = dict(zip(cols, r))
            d["status"] = "active"
            results.append(d)

    sql = "SELECT * FROM position_archive"
    params = []
    if date:
        sql += " WHERE closed_date = ?"
        params.append(date)
    sql += " ORDER BY closed_date DESC, code"
    rows = db.conn.execute(sql, params).fetchall()
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(position_archive)").fetchall()]
    for r in rows:
        d = dict(zip(cols, r))
        d["status"] = "closed"
        results.append(d)

    return results


def delete_position(code: str) -> bool:
    db = _ensure_db()
    db.conn.execute("DELETE FROM position WHERE code=?", (code,))
    db.conn.commit()
    return True


def archive_position(code: str, closed_price: float = 0, realized_pnl: float = None,
                     realized_pnl_pct: float = None, closed_date: str = None) -> bool:
    """将当前持仓归档到 position_archive，保留已清仓记录供日后查询。"""
    db = _ensure_db()
    pos = get_position(code)
    if not pos:
        return False
    try:
        now = _now_ts()
        cd = closed_date or _now()
        db.conn.execute(
            """INSERT INTO position_archive
               (code, name, avg_cost, total_qty, available_qty, first_buy_date,
                last_trade_date, closed_date, closed_price, realized_pnl,
                realized_pnl_pct, strategy, notes, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (pos.get("code"), pos.get("name"), pos.get("avg_cost"),
             pos.get("total_qty"), pos.get("available_qty"),
             pos.get("first_buy_date"), pos.get("last_trade_date"),
             cd, closed_price, realized_pnl, realized_pnl_pct,
             pos.get("strategy"), pos.get("notes"), now)
        )
        db.conn.commit()
        return True
    except Exception:
        return False


def snapshot_position(code: str, name: str = "", qty: int = 0, avg_cost: float = 0,
                      close_price: float = 0, indicators: dict = None) -> bool:
    """记录当日持仓快照"""
    db = _ensure_db()
    market_value = qty * close_price if qty and close_price else 0
    unrealized_pnl = (close_price - avg_cost) * qty if qty and avg_cost and close_price else 0
    unrealized_pnl_pct = (close_price - avg_cost) / avg_cost * 100 if avg_cost and close_price else 0
    try:
        db.conn.execute(
            """INSERT OR REPLACE INTO position_snapshot
               (date, code, name, qty, avg_cost, close_price, market_value,
                unrealized_pnl, unrealized_pnl_pct, indicators)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), code, name, qty, avg_cost, close_price, round(market_value, 2),
             round(unrealized_pnl, 2), round(unrealized_pnl_pct, 2),
             _safe_json(indicators))
        )
        db.conn.commit()
        return True
    except Exception:
        return False


# ============================================================
# 交易流水 Transaction
# ============================================================

def add_transaction(code: str, trade_date: str, direction: str, qty: int, price: float,
                    name: str = "", fee: float = 0, reason: str = "", memo: str = "",
                    pnl: float = None) -> Optional[int]:
    """新增交易记录，自动更新持仓头寸。返回 transaction id。"""
    db = _ensure_db()
    amount = qty * price
    pos = get_position(code) or {}

    # 计算交易后状态
    old_qty = pos.get("total_qty", 0)
    old_cost = pos.get("avg_cost", 0)
    if direction in ("buy", "t_buy"):
        new_qty = old_qty + qty
        new_cost = round((old_cost * old_qty + amount) / new_qty, 3) if new_qty else price
        balance_qty = new_qty
        _pnl = None
        _pnl_pct = None
    elif direction in ("sell", "t_sell", "clear"):
        new_qty = max(0, old_qty - qty)
        new_cost = old_cost if new_qty else 0
        balance_qty = new_qty
        _pnl = pnl or round((price - old_cost) * qty, 2)
        _pnl_pct = round((price - old_cost) / old_cost * 100, 2) if old_cost else None
    else:
        return None

    avg_cost_after = new_cost if new_qty else 0
    stock_name = name or pos.get("name", code)

    try:
        now = _now_ts()
        cur = db.conn.execute(
            """INSERT INTO trade_record (code, name, trade_date, direction, qty, price,
               amount, fee, pnl, pnl_pct, balance_qty, avg_cost_after, reason, memo, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, stock_name, trade_date, direction, qty, price, amount, fee,
             _pnl, _pnl_pct, balance_qty, avg_cost_after, reason, memo, now)
        )
        tx_id = cur.lastrowid

        if new_qty <= 0:
            archive_position(code, closed_price=price, realized_pnl=_pnl,
                             realized_pnl_pct=_pnl_pct, closed_date=trade_date)
            db.conn.execute("DELETE FROM position WHERE code=?", (code,))
            _audit("position", code, "DELETE", json.dumps(pos), None, f"{direction}清仓")
        else:
            if pos:
                db.conn.execute(
                    """UPDATE position SET avg_cost=?, total_qty=?, available_qty=?,
                       last_trade_date=?, updated_at=? WHERE code=?""",
                    (avg_cost_after, new_qty, new_qty, trade_date, now, code)
                )
                _audit("position", code, "UPDATE",
                       json.dumps({"avg_cost": old_cost, "total_qty": old_qty}),
                       json.dumps({"avg_cost": avg_cost_after, "total_qty": new_qty}),
                       f"{direction} qty={qty} price={price}")
            else:
                add_position(code, stock_name, price, new_qty, strategy=reason or "")

        db.conn.commit()
        return tx_id
    except Exception:
        return None


def list_transactions(code: str = None, days: int = 90, limit: int = 500) -> List[dict]:
    db = _ensure_db()
    sql = "SELECT * FROM trade_record"
    params = []
    conditions = []
    if code:
        conditions.append("code=?")
        params.append(code)
    if days > 0:
        cutoff = f"{_now()[:4]}-{int(_now()[5:7]) - days // 30:02d}-{_now()[8:]}"
        conditions.append("trade_date >= ?")
        params.append(cutoff)
    if conditions:
        sql += " WHERE " + " AND ".join(conditions)
    sql += " ORDER BY trade_date DESC, id DESC LIMIT ?"
    params.append(limit)
    rows = db.conn.execute(sql, params).fetchall()
    if not rows:
        return []
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(trade_record)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def get_pnl_summary(days: int = 30) -> dict:
    """近期盈亏汇总"""
    db = _ensure_db()
    start = _now() if days <= 0 else f"{_now()[:4]}-{max(1, int(_now()[5:7]) - 1):02d}-01"
    row = db.conn.execute(
        """SELECT COUNT(*) as trades, COALESCE(SUM(pnl), 0) as total_pnl,
           COALESCE(AVG(pnl_pct), 0) as avg_pnl_pct
           FROM trade_record WHERE direction IN ('sell','t_sell','clear')
           AND trade_date >= ?""",
        (start,)
    ).fetchone()
    return {"trades": row[0], "total_pnl": round(row[1] or 0, 2), "avg_pnl_pct": round(row[2] or 0, 2)}


def get_position_adjustment_summary(code: str, date: str = None) -> dict:
    """返回某股票在某日的调仓摘要：开盘持仓、收盘持仓、买卖数量、成本变化。
    用于复刻截图中的"从 400 股 → 600 股，成本升至 14.02"这类调仓对比。"""
    db = _ensure_db()
    date = date or _now()
    rows = db.conn.execute(
        """SELECT direction, qty, price, avg_cost_after, balance_qty, pnl
           FROM trade_record WHERE code=? AND trade_date=? ORDER BY id""",
        (code, date)
    ).fetchall()
    if not rows:
        return {}

    first = rows[0]
    last = rows[-1]

    # 反推开盘持仓（第一笔交易前）
    if first[0] in ("buy", "t_buy"):
        start_qty = first[4] - first[1]
    else:
        start_qty = first[4] + first[1]

    close_qty = last[4]
    buys = sum(r[1] for r in rows if r[0] in ("buy", "t_buy"))
    sells = sum(r[1] for r in rows if r[0] in ("sell", "t_sell", "clear"))
    realized_pnl = sum(r[5] for r in rows if r[5] is not None)

    # 找昨天的收盘成本作为 old_cost
    prev = db.conn.execute(
        """SELECT avg_cost_after FROM trade_record
           WHERE code=? AND trade_date < ? ORDER BY trade_date DESC, id DESC LIMIT 1""",
        (code, date)
    ).fetchone()
    old_cost = prev[0] if prev else None
    new_cost = last[3] if close_qty > 0 else None

    action = "不变"
    if close_qty <= 0 and sells > 0:
        action = "清仓"
    elif buys > 0 and sells == 0:
        action = "加仓"
    elif sells > 0 and buys == 0 and close_qty > 0:
        action = "减仓"
    elif buys > 0 and sells > 0:
        action = "调仓"

    return {
        "code": code,
        "date": date,
        "action": action,
        "start_qty": start_qty,
        "close_qty": close_qty,
        "buy_qty": buys,
        "sell_qty": sells,
        "old_cost": old_cost,
        "new_cost": new_cost,
        "realized_pnl": round(realized_pnl, 2),
    }


def get_daily_position_changes(date: str = None) -> List[dict]:
    """生成某日持仓变动小结：加仓/减仓/清仓/不变。
    基于当日交易流水反推。当天无交易但仍有持仓的标的不在此列表（视为不变）。"""
    db = _ensure_db()
    date = date or _now()
    rows = db.conn.execute(
        """SELECT code, name, direction, qty, price, avg_cost_after, balance_qty, pnl
           FROM trade_record WHERE trade_date=? ORDER BY id""",
        (date,)
    ).fetchall()

    from collections import defaultdict
    code_txs = defaultdict(list)
    for r in rows:
        code_txs[r[0]].append({
            "name": r[1], "direction": r[2], "qty": r[3],
            "price": r[4], "avg_cost_after": r[5], "balance_qty": r[6], "pnl": r[7]
        })

    changes = []
    for code, txs in code_txs.items():
        summary = get_position_adjustment_summary(code, date)
        if summary:
            changes.append(summary)
    return changes


# ============================================================
# 关注列表 Watchlist
# ============================================================

def add_to_watchlist(code: str, name: str = "", source: str = "manual", reason: str = "",
                     priority: int = 3, tags: list = None, added_price: float = None,
                     notes: str = "", level: int = 2) -> int:
    """加入关注列表。level=1重点, level=2普通。返回 1=新增, 2=更新, 0=失败。"""
    db = _ensure_db()
    try:
        existing = db.conn.execute("SELECT code, status FROM watchlist WHERE code=?", (code,)).fetchone()
        if existing:
            cur_status = existing[1]
            new_status = "active" if cur_status in ("archived",) else cur_status
            db.conn.execute(
                """UPDATE watchlist SET name=?, source=?, reason=?, priority=?, tags=?,
                   notes=?, status=?, level=? WHERE code=?""",
                (name, source, reason, priority, _safe_json(tags), notes, new_status, level, code)
            )
            db.conn.commit()
            return 2
        else:
            db.conn.execute(
                """INSERT INTO watchlist (code, name, source, reason, priority, tags, status,
                   added_date, added_price, notes, level)
                   VALUES (?, ?, ?, ?, ?, ?, 'active', ?, ?, ?, ?)""",
                (code, name, source, reason, priority, _safe_json(tags),
                 _now(), added_price, notes, level)
            )
            db.conn.commit()
            return 1
    except Exception:
        return 0


def set_watchlist_level(code: str, level: int) -> bool:
    """设置关注层级 1=重点 2=普通"""
    db = _ensure_db()
    try:
        db.conn.execute("UPDATE watchlist SET level=? WHERE code=?", (level, code))
        db.conn.commit()
        return db.conn.total_changes > 0
    except Exception:
        return False


def list_watchlist(status: str = "active") -> List[dict]:
    db = _ensure_db()
    sql = "SELECT * FROM watchlist"
    params = []
    if status:
        sql += " WHERE status=?"
        params.append(status)
    sql += " ORDER BY priority ASC, code ASC"
    rows = db.conn.execute(sql, params).fetchall()
    if not rows:
        return []
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(watchlist)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def get_watchlist_item(code: str) -> Optional[dict]:
    db = _ensure_db()
    row = db.conn.execute("SELECT * FROM watchlist WHERE code=?", (code,)).fetchone()
    if not row:
        return None
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(watchlist)").fetchall()]
    return dict(zip(cols, row))


def update_watchlist_status(code: str, status: str, reason: str = "") -> bool:
    """更新关注状态（active/observing/archived）"""
    db = _ensure_db()
    try:
        if status == "archived":
            db.conn.execute(
                "UPDATE watchlist SET status=?, archived_date=?, archived_reason=? WHERE code=?",
                (status, _now(), reason, code)
            )
        else:
            db.conn.execute(
                "UPDATE watchlist SET status=?, archived_date=NULL, archived_reason=NULL WHERE code=?",
                (status, code)
            )
        db.conn.commit()
        _audit("watchlist", code, "UPDATE", None, f"status={status}", reason)
        return True
    except Exception:
        return False


def remove_from_watchlist(code: str, reason: str = "") -> bool:
    return update_watchlist_status(code, "archived", reason)


def record_watchlist_daily(code: str, indicators: dict) -> bool:
    """记录关注票每日指标快照"""
    db = _ensure_db()
    sigs = indicators.get("信号", [])
    try:
        db.conn.execute(
            """INSERT OR REPLACE INTO watchlist_daily
               (date, code, close, change_pct, J, RSI, 趋势, 白线, 黄线, 评分,
                B1_active, near_B1, signals, 超缩量, 洗盘异动, status_change)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), code,
             indicators.get("last"), indicators.get("change_pct"),
             indicators.get("J"), indicators.get("RSI"),
             indicators.get("趋势"), indicators.get("白线"), indicators.get("黄线"),
             indicators.get("评分"),
             1 if sigs else 0,
             1 if indicators.get("J", 999) < 20 else 0,
             _safe_json(sigs),
             1 if indicators.get("超缩量") else 0,
             1 if indicators.get("洗盘异动") else 0,
             "")
        )
        db.conn.commit()
        return True
    except Exception:
        return False


def detect_watchlist_changes(code: str) -> dict:
    """对比昨日今日关注票指标变化"""
    db = _ensure_db()
    today = _now()
    rows = db.conn.execute(
        """SELECT date, J, 评分, 趋势, signals, B1_active, near_B1 FROM watchlist_daily
           WHERE code=? ORDER BY date DESC LIMIT 2""",
        (code,)
    ).fetchall()
    if len(rows) < 2:
        return {"code": code, "changed": False, "changes": []}

    t, y = rows[0], rows[1]
    changes = []
    if abs(t[1] - y[1]) > 3:
        changes.append(f"J: {y[1]}→{t[1]}")
    if t[2] != y[2]:
        changes.append(f"评分: {y[2]}→{t[2]}")
    if t[3] != y[3]:
        changes.append(f"趋势: {y[3]}→{t[3]}")
    if t[4] != y[4]:
        old_sigs = json.loads(y[4]) if y[4] else []
        new_sigs = json.loads(t[4]) if t[4] else []
        if set(new_sigs) != set(old_sigs):
            changes.append(f"信号变化: {old_sigs}→{new_sigs}")
    if t[5] != y[5]:
        changes.append("B1激活" if t[5] else "B1消失")
    if t[6] != y[6]:
        changes.append("进入近B1" if t[6] else "离开近B1")
    return {"code": code, "changed": bool(changes), "changes": changes}


# ============================================================
# B1 追踪
# ============================================================

def record_b1_scan(scan_type: str, sector_name: str = "", total: int = 0,
                   b1: int = 0, near: int = 0, report_path: str = "",
                   elapsed: float = 0) -> int:
    """记录一次扫描批次。返回 scan_id。"""
    db = _ensure_db()
    try:
        cur = db.conn.execute(
            """INSERT INTO b1_scan (scan_date, scan_type, sector_name, total_scanned,
               b1_count, near_b1_count, report_path, elapsed_sec, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), scan_type, sector_name, total, b1, near, report_path, elapsed, _now_ts())
        )
        db.conn.commit()
        return cur.lastrowid
    except Exception:
        return 0


def add_b1_candidate(scan_id: int, code: str, name: str = "", sector: str = "",
                     category: str = "", result: dict = None) -> bool:
    """新增一条 B1 候选明细"""
    db = _ensure_db()
    r = result or {}
    try:
        db.conn.execute(
            """INSERT INTO b1_candidate (scan_id, code, name, sector, scan_date, category,
               close, change_pct, J, 趋势, 评分, signals, 单针下20, 超缩量,
               距离白线_pct, 距离黄线_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (scan_id, code, name, sector or r.get("sector", ""), _now(), category,
             r.get("last"), r.get("change_pct"), r.get("J"), r.get("趋势"),
             r.get("评分"), _safe_json(r.get("信号", [])),
             1 if r.get("单针下20") else 0,
             1 if r.get("超缩量") else 0,
             r.get("距离白线_pct"), r.get("距离黄线_pct"))
        )
        db.conn.commit()
        return True
    except Exception:
        return False


def update_b1_stage(code: str, stage: str, indicators: dict = None, memo: str = "") -> bool:
    """更新或插入一条 B1 状态追踪记录"""
    db = _ensure_db()
    ind = indicators or {}
    try:
        prev = db.conn.execute(
            "SELECT stage, stage_days FROM b1_tracking WHERE code=? ORDER BY date DESC LIMIT 1",
            (code,)
        ).fetchone()
        stage_days = 1
        if prev and prev[0] == stage:
            stage_days = (prev[1] or 0) + 1

        db.conn.execute(
            """INSERT OR REPLACE INTO b1_tracking
               (code, date, stage, J, close, signals, trend, score, stage_days, memo)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (code, _now(), stage,
             ind.get("J"), ind.get("last"),
             _safe_json(ind.get("信号", [])),
             ind.get("趋势"),
             ind.get("评分"),
             stage_days, memo)
        )
        db.conn.commit()
        return True
    except Exception:
        return False


def get_b1_tracking(code: str, limit: int = 30) -> List[dict]:
    db = _ensure_db()
    rows = db.conn.execute(
        "SELECT * FROM b1_tracking WHERE code=? ORDER BY date DESC LIMIT ?",
        (code, limit)
    ).fetchall()
    if not rows:
        return []
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(b1_tracking)").fetchall()]
    return [dict(zip(cols, r)) for r in reversed(rows)]


def get_expired_observing(days: int = 7) -> List[str]:
    """查找观察期超过 days 天仍未恢复 B1 的票"""
    db = _ensure_db()
    rows = db.conn.execute(
        """SELECT code, MAX(date) as last_date, stage FROM b1_tracking
           WHERE stage='observing' GROUP BY code HAVING COUNT(*) >= ?""",
        (days,)
    ).fetchall()
    return [r[0] for r in rows]


# ============================================================
# 重点板块 Focus Sector
# ============================================================

def add_focus_sector(name: str, sector_type: str = "industry", source: str = "manual",
                     priority: int = 3, notes: str = "", tags: list = None) -> int:
    db = _ensure_db()
    try:
        existing = db.conn.execute("SELECT name FROM focus_sector WHERE name=?", (name,)).fetchone()
        if existing:
            db.conn.execute(
                """UPDATE focus_sector SET sector_type=?, source=?, priority=?, notes=?,
                   tags=?, status='active' WHERE name=?""",
                (sector_type, source, priority, notes, _safe_json(tags), name)
            )
            db.conn.commit()
            return 2
        else:
            db.conn.execute(
                """INSERT INTO focus_sector (name, sector_type, source, priority, notes, tags,
                   added_date, status)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'active')""",
                (name, sector_type, source, priority, notes, _safe_json(tags), _now())
            )
            db.conn.commit()
            return 1
    except Exception:
        return 0


def list_focus_sectors(status: str = "active") -> List[dict]:
    db = _ensure_db()
    sql = "SELECT * FROM focus_sector"
    if status:
        sql += " WHERE status=?"
    sql += " ORDER BY priority ASC"
    rows = db.conn.execute(sql, (status,) if status else ()).fetchall()
    if not rows:
        return []
    cols = [c[1] for c in db.conn.execute("PRAGMA table_info(focus_sector)").fetchall()]
    return [dict(zip(cols, r)) for r in rows]


def record_focus_daily(name: str, change_pct: float = None, flow_in: float = None,
                       leading_stock: str = "", b1_count: int = 0, near_b1_count: int = 0,
                       avg_score: float = None, hot_rank: int = None) -> bool:
    db = _ensure_db()
    try:
        db.conn.execute(
            """INSERT OR REPLACE INTO focus_sector_daily
               (date, name, change_pct, flow_in, leading_stock, b1_count, near_b1_count,
                avg_score, hot_rank)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (_now(), name, change_pct, flow_in, leading_stock, b1_count, near_b1_count,
             avg_score, hot_rank)
        )
        db.conn.commit()
        return True
    except Exception:
        return False


# ============================================================
# 审计日志
# ============================================================

# ============================================================
# 账户快照
# ============================================================

def save_account_snapshot(total_asset: float, available_cash: float, stock_value: float,
                          position_ratio: float = 0, total_pnl: float = 0, total_pnl_pct: float = 0) -> bool:
    db = _ensure_db()
    date = datetime.now().strftime("%Y-%m-%d")
    try:
        db.conn.execute(
            """INSERT OR REPLACE INTO account_snapshot
               (date, total_asset, available_cash, stock_value, position_ratio, total_pnl, total_pnl_pct, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (date, total_asset, available_cash, stock_value, position_ratio, total_pnl, total_pnl_pct, _now_ts())
        )
        db.conn.commit()
        return True
    except Exception:
        return False


def get_latest_account() -> dict | None:
    db = _ensure_db()
    row = db.conn.execute(
        "SELECT date, total_asset, available_cash, stock_value, position_ratio, total_pnl, total_pnl_pct "
        "FROM account_snapshot ORDER BY date DESC LIMIT 1"
    ).fetchone()
    if row:
        return {
            "date": row[0], "total_asset": row[1], "available_cash": row[2],
            "stock_value": row[3], "position_ratio": row[4], "total_pnl": row[5], "total_pnl_pct": row[6],
        }
    return None


def _audit(table: str, record_id: str, action: str, old_val: Any = None,
           new_val: Any = None, reason: str = "", operator: str = "system"):
    db = _ensure_db()
    try:
        db.conn.execute(
            """INSERT INTO audit_log (table_name, record_id, action, old_value, new_value,
               reason, operator, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (table, str(record_id), action,
             json.dumps(old_val, ensure_ascii=False) if old_val and not isinstance(old_val, str) else (old_val or ""),
             json.dumps(new_val, ensure_ascii=False) if new_val and not isinstance(new_val, str) else (new_val or ""),
             reason, operator, _now_ts())
        )
        db.conn.commit()
    except Exception:
        pass
