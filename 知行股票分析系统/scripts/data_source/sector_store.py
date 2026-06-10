"""
东财板块数据存储 — 行业/概念板块成分股缓存

用法:
    from data_source.sector_store import update_sector, get_sector_members
    update_sector("光模块", kind="concept")         # 从东财拉取+缓存
    members = get_sector_members("光模块")           # 从缓存读取
"""
import time
import random
from datetime import datetime
from typing import List, Optional

from storage.db import get_db


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def update_sector(name: str, kind: str = "concept") -> int:
    """从东财 API 拉取板块成分股并缓存。返回写入条数。"""
    db = get_db()

    # 东财→efinance→sector_index→theme_chains 四级降级
    members = _try_akshare(name, kind) or _try_efinance(name, kind)

    if not members:
        members = _try_sector_index_db(name)

    if not members:
        members = _try_theme_chains_stocks(name)

    if not members:
        return 0

    now = _now()
    count = 0
    for code, stock_name in members:
        db.conn.execute(
            "INSERT OR REPLACE INTO sector_stock (sector_name, sector_type, code, name, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, kind, code, stock_name, now),
        )
        count += 1
    db.conn.commit()
    return count


def get_sector_members(name: str, kind: str = "concept") -> List[dict]:
    """从缓存获取板块成分股"""
    db = get_db()
    rows = db.conn.execute(
        "SELECT code, name FROM sector_stock WHERE sector_name=? AND sector_type=?",
        (name, kind),
    ).fetchall()
    return [{"code": r[0], "name": r[1]} for r in rows]


def list_sectors(kind: str = None) -> List[dict]:
    """列出已缓存的板块"""
    db = get_db()
    if kind:
        rows = db.conn.execute(
            "SELECT DISTINCT sector_name, sector_type, MAX(updated_at) FROM sector_stock "
            "WHERE sector_type=? GROUP BY sector_name ORDER BY sector_name",
            (kind,),
        ).fetchall()
    else:
        rows = db.conn.execute(
            "SELECT DISTINCT sector_name, sector_type, MAX(updated_at) FROM sector_stock "
            "GROUP BY sector_name, sector_type ORDER BY sector_type, sector_name",
        ).fetchall()
    return [{"name": r[0], "type": r[1], "updated": r[2]} for r in rows]


def update_all_from_theme_chains() -> int:
    """从 theme_chains.py 的映射表全量更新板块数据"""
    from config.theme_chains import CONCEPT_SECTOR_MAP, INDUSTRY_SECTOR_MAP

    total = 0
    seen = set()

    for sector_name in CONCEPT_SECTOR_MAP.values():
        if sector_name in seen:
            continue
        seen.add(sector_name)
        time.sleep(random.uniform(2.0, 4.0))
        n = update_sector(sector_name, "concept")
        print(f"  {sector_name}: {n} 只")
        total += n

    for sector_name in INDUSTRY_SECTOR_MAP.values():
        if sector_name in seen:
            continue
        seen.add(sector_name)
        time.sleep(random.uniform(2.0, 4.0))
        n = update_sector(sector_name, "industry")
        print(f"  {sector_name}: {n} 只")
        total += n

    return total


# ============================================================
# 内部 — 东财API拉取
# ============================================================


def _try_akshare(name: str, kind: str) -> Optional[List[tuple]]:
    try:
        import akshare as ak
        time.sleep(random.uniform(1.5, 3.0))
        if kind == "concept":
            df = ak.stock_board_concept_cons_em(symbol=name)
        else:
            df = ak.stock_board_industry_cons_em(symbol=name)
        if df is None or df.empty:
            return None
        return [(str(r["代码"]).split(".")[0], str(r["名称"])) for _, r in df.iterrows()]
    except Exception:
        return None


def _try_sector_index_db(name: str) -> Optional[List[tuple]]:
    """sector_index 降级：按证监会行业名查成分股"""
    try:
        db = get_db()
        rows = db.conn.execute(
            "SELECT si.code, COALESCE(si2.name,'') FROM sector_index si "
            "LEFT JOIN stock_info si2 ON si.code=si2.code "
            "WHERE si.sector_name=? ORDER BY si.code", (name,)
        ).fetchall()
        if rows:
            print(f"  [sector_index] {name}: {len(rows)}只")
            return [(r[0], r[1]) for r in rows]
    except Exception:
        pass
    return None


def _try_theme_chains_stocks(name: str) -> Optional[List[tuple]]:
    """theme_chains.py 硬编码标的兜底"""
    try:
        from config.theme_chains import THEME_CHAINS, resolve_theme
        theme_name, chain = resolve_theme(name)
        if not chain:
            return None
        codes = []
        for code_list in chain.values():
            codes.extend(code_list)
        codes = list(dict.fromkeys(codes))
        print(f"  [theme_chains] {name}: {len(codes)}只")
        return [(c, "") for c in codes]
    except Exception:
        return None


def _try_efinance(name: str, kind: str) -> Optional[List[tuple]]:
    try:
        import efinance as ef
        time.sleep(random.uniform(1.5, 3.0))
        if kind == "concept":
            df = ef.stock.get_belong_board(name)
        else:
            df = ef.stock.get_realtime_quotes(["行业板块"])
        if df is None or df.empty:
            return None
        return [(str(r.get("股票代码", r.get("code", ""))).split(".")[0],
                 str(r.get("股票名称", r.get("name", "")))) for _, r in df.iterrows()]
    except Exception:
        return None
