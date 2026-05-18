"""
SQLite 本地 K 线数据库
单文件，无外部依赖，Python 标准库 sqlite3
"""
import sqlite3
import os
from datetime import date
from typing import List, Optional


DB_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "data", "kline.db"
)


SCHEMA = """
CREATE TABLE IF NOT EXISTS stock_daily (
    code   TEXT NOT NULL,
    date   TEXT NOT NULL,   -- '2026-05-19'
    open   REAL,
    high   REAL,
    low    REAL,
    close  REAL,
    volume REAL,            -- 手
    PRIMARY KEY (code, date)
);

CREATE INDEX IF NOT EXISTS idx_code_date ON stock_daily(code, date);

CREATE TABLE IF NOT EXISTS trading_calendar (
    date TEXT PRIMARY KEY
);
"""


class StockDB:
    """K 线数据库"""

    def __init__(self, path: str = None):
        self.path = path or DB_PATH
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        self._conn = None
        self._calendar_lock = __import__('threading').Lock()

    @property
    def conn(self):
        if self._conn is None:
            self._conn = sqlite3.connect(self.path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()
        return self._conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ============================================================
    # 写入
    # ============================================================

    def upsert(self, code: str, rows: List[dict]) -> int:
        """
        批量插入或更新。rows 格式: [{date, open, high, low, close, volume}, ...]
        返回实际写入行数。
        """
        count = 0
        with self.conn:
            for r in rows:
                self.conn.execute(
                    """INSERT OR REPLACE INTO stock_daily (code, date, open, high, low, close, volume)
                       VALUES (?, ?, ?, ?, ?, ?, ?)""",
                    (code, r["date"], r.get("open"), r.get("high"),
                     r.get("low"), r.get("close"), r.get("volume"))
                )
                count += 1
        return count

    def upsert_candles(self, code: str, candles: List[dict]) -> int:
        """便利方法：candles 格式兼容 b1_calculator 的输入"""
        return self.upsert(code, candles)

    # ============================================================
    # 查询
    # ============================================================

    def get_candles(self, code: str, limit: int = 120) -> List[dict]:
        """取最近 N 天 K 线，返回 candles 格式"""
        rows = self.conn.execute(
            "SELECT date, open, high, low, close, volume FROM stock_daily "
            "WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, limit)
        ).fetchall()
        # 按日期升序返回（B1 计算器需要）
        rows.reverse()
        return [
            {"date": r[0], "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": r[5]}
            for r in rows
        ]

    def get_last_date(self, code: str) -> Optional[str]:
        """某只股票最新数据的日期"""
        row = self.conn.execute(
            "SELECT MAX(date) FROM stock_daily WHERE code=?", (code,)
        ).fetchone()
        return row[0] if row and row[0] else None

    def get_missing_dates(self, code: str, trading_days: List[str]) -> List[str]:
        """
        给定交易日列表，返回该股票缺失的日期。
        用于增量更新：date_sequence 获取交易日历 → 此方法找出缺口。
        """
        if not trading_days:
            return []
        placeholders = ','.join('?' * len(trading_days))
        existing = set(r[0] for r in self.conn.execute(
            f"SELECT date FROM stock_daily WHERE code=? AND date IN ({placeholders})",
            [code] + trading_days
        ).fetchall())
        return [d for d in trading_days if d not in existing]

    # ============================================================
    # 交易日历
    # ============================================================

    def ensure_trading_calendar(self, start: str = "2025-01-01", end: str = None) -> int:
        """
        从 date_sequence 获取交易日历并缓存。
        已有数据不重复拉取。返回新增天数。（线程安全）
        """
        from datetime import datetime
        if end is None:
            end = datetime.now().strftime("%Y-%m-%d")

        with self._calendar_lock:
            # 双重检查：锁内再查一次
            last = self.conn.execute("SELECT MAX(date) FROM trading_calendar").fetchone()
            if last and last[0] and str(last[0]) >= end:
                return 0

            print(f"  [calendar] 更新交易日历 {start} ~ {end}...")
            from data_source.ifind_client import IFindClient
            client = IFindClient()
            data = client._http(
                "/date_sequence",
                {"codes": "000001.SH", "startdate": start, "enddate": end,
                 "functionpara": {"Days": "Tradedays", "Fill": "Omit"},
                 "indipara": [{"indicator": "ths_close_price_stock", "indiparams": ["", "", ""]}]},
                timeout=15
            )
            if not data or data.get("errorcode") != 0:
                return 0

            tables = data.get("tables", [])
            if not tables:
                return 0

            days = tables[0].get("time", [])
            count = 0
            with self.conn:
                for d in days:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO trading_calendar (date) VALUES (?)", (d[:10],)
                    )
                    count += 1
            print(f"  [calendar] 新增 {count} 个交易日")
            return count

    def get_trading_days(self, start: str, end: str) -> List[str]:
        """从本地缓存取交易日列表"""
        self.ensure_trading_calendar()
        rows = self.conn.execute(
            "SELECT date FROM trading_calendar WHERE date >= ? AND date <= ? ORDER BY date",
            (start, end)
        ).fetchall()
        return [r[0] for r in rows]

    def get_last_trading_day(self, before: str = None) -> Optional[str]:
        """最近一个交易日"""
        from datetime import datetime
        if before is None:
            before = datetime.now().strftime("%Y-%m-%d")
        row = self.conn.execute(
            "SELECT MAX(date) FROM trading_calendar WHERE date <= ?", (before,)
        ).fetchone()
        return row[0] if row else None

    # ============================================================
    # 统计
    # ============================================================

    @property
    def stock_count(self) -> int:
        """库里有多少只股票"""
        row = self.conn.execute(
            "SELECT COUNT(DISTINCT code) FROM stock_daily"
        ).fetchone()
        return row[0] if row else 0

    @property
    def total_rows(self) -> int:
        """库里总共多少条日线记录"""
        row = self.conn.execute(
            "SELECT COUNT(*) FROM stock_daily"
        ).fetchone()
        return row[0] if row else 0

    def stock_stats(self, code: str) -> dict:
        """某只股票的统计信息"""
        row = self.conn.execute(
            "SELECT MIN(date), MAX(date), COUNT(*) FROM stock_daily WHERE code=?",
            (code,)
        ).fetchone()
        return {
            "code": code,
            "first_date": row[0],
            "last_date": row[1],
            "days": row[2],
        }


# 全局单例
_db = None


def get_db(path: str = None) -> StockDB:
    global _db
    if _db is None:
        _db = StockDB(path)
    return _db
