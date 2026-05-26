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
    amount REAL,            -- 成交额(元)
    turnover REAL,          -- 换手率(%)
    amplitude REAL,         -- 振幅(%)
    change_pct REAL,        -- 涨跌幅(%)
    PRIMARY KEY (code, date)
);

CREATE INDEX IF NOT EXISTS idx_code_date ON stock_daily(code, date);

CREATE TABLE IF NOT EXISTS trading_calendar (
    date TEXT PRIMARY KEY
);

-- ============================================================
-- 持仓账务
-- ============================================================

CREATE TABLE IF NOT EXISTS position (
    code            TEXT PRIMARY KEY,
    name            TEXT,
    avg_cost        REAL,                -- 加权平均成本价
    total_qty       INTEGER,             -- 当前总股数
    available_qty   INTEGER,             -- 可用股数
    first_buy_date  TEXT,                -- 首次买入日期
    last_trade_date TEXT,                -- 最后交易日期
    strategy        TEXT,                -- 长线/短线/波段/套利
    notes           TEXT,                -- 备注
    stop_loss       REAL,                -- 止损价
    target_price    REAL,                -- 目标价
    updated_at      TEXT                 -- 最后更新时间
);

CREATE TABLE IF NOT EXISTS trade_record (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT NOT NULL,
    name          TEXT,
    trade_date    TEXT NOT NULL,          -- YYYY-MM-DD
    direction     TEXT NOT NULL,          -- buy / sell / t_buy / t_sell / clear
    qty           INTEGER NOT NULL,
    price         REAL NOT NULL,
    amount        REAL,                   -- qty * price
    fee           REAL DEFAULT 0,
    pnl           REAL,                   -- 实现盈亏（卖出时计算）
    pnl_pct       REAL,                   -- 实现盈亏比例
    balance_qty   INTEGER,                -- 交易后持仓余量
    avg_cost_after REAL,                  -- 交易后成本
    reason        TEXT,                   -- 交易理由
    memo          TEXT,                   -- 补充说明
    created_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_tx_code ON trade_record(code);
CREATE INDEX IF NOT EXISTS idx_tx_date ON trade_record(trade_date);

-- ============================================================
-- 账户快照
-- ============================================================

CREATE TABLE IF NOT EXISTS account_snapshot (
    date              TEXT PRIMARY KEY,
    total_asset       REAL,                -- 总资产
    available_cash    REAL,                -- 可用资金
    stock_value       REAL,                -- 股票市值
    position_ratio    REAL,                -- 仓位 (%)
    total_pnl         REAL,                -- 总盈亏
    total_pnl_pct     REAL,                -- 总盈亏比例
    created_at        TEXT
);

CREATE TABLE IF NOT EXISTS position_snapshot (
    date          TEXT NOT NULL,
    code          TEXT NOT NULL,
    name          TEXT,
    qty           INTEGER,
    avg_cost      REAL,
    close_price   REAL,                   -- 当日收盘价
    market_value  REAL,                   -- 市值
    unrealized_pnl REAL,                  -- 浮动盈亏
    unrealized_pnl_pct REAL,              -- 浮动盈亏比例
    indicators    TEXT,                   -- JSON: 指标快照
    PRIMARY KEY (date, code)
);

-- ============================================================
-- 关注列表
-- ============================================================

CREATE TABLE IF NOT EXISTS watchlist (
    code          TEXT PRIMARY KEY,
    name          TEXT,
    source        TEXT DEFAULT 'manual',  -- manual / auto_scan / recommend
    reason        TEXT,
    priority      INTEGER DEFAULT 3,      -- 1-5, 1=最高
    tags          TEXT,                   -- JSON: ["锂电池","B1观察"]
    status        TEXT DEFAULT 'active',  -- active / observing / archived
    added_date    TEXT,
    added_price   REAL,
    notes         TEXT,
    archived_date TEXT,
    archived_reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_wl_status ON watchlist(status);

CREATE TABLE IF NOT EXISTS watchlist_daily (
    date          TEXT NOT NULL,
    code          TEXT NOT NULL,
    close         REAL,
    change_pct    REAL,
    J             REAL,
    RSI           REAL,
    趋势          TEXT,
    白线          REAL,
    黄线          REAL,
    评分          INTEGER,
    B1_active     INTEGER DEFAULT 0,      -- 0/1
    near_B1       INTEGER DEFAULT 0,      -- J<20
    signals       TEXT,                   -- JSON: 信号列表
    超缩量        INTEGER DEFAULT 0,
    洗盘异动      INTEGER DEFAULT 0,
    status_change TEXT,                   -- new_B1 / J_dropped / trend_bear / improved / worsened / ''
    PRIMARY KEY (date, code)
);
CREATE INDEX IF NOT EXISTS idx_wld_code ON watchlist_daily(code, date);

-- ============================================================
-- B1 追踪
-- ============================================================

CREATE TABLE IF NOT EXISTS b1_scan (
    scan_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_date     TEXT,
    scan_type     TEXT,                   -- sector / market / holdings
    sector_name   TEXT,
    total_scanned INTEGER,
    b1_count      INTEGER,
    near_b1_count INTEGER,
    report_path   TEXT,
    feishu_url    TEXT,
    elapsed_sec   REAL,
    created_at    TEXT
);

CREATE TABLE IF NOT EXISTS b1_candidate (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id       INTEGER NOT NULL,
    code          TEXT NOT NULL,
    name          TEXT,
    sector        TEXT,
    scan_date     TEXT,
    category      TEXT,                   -- B1 / near_B1 / trend_hold / suo_bao
    close         REAL,
    change_pct    REAL,
    J             REAL,
    趋势          TEXT,
    评分          INTEGER,
    signals       TEXT,                   -- JSON
    单针下20      INTEGER DEFAULT 0,
    超缩量        INTEGER DEFAULT 0,
    距离白线_pct  REAL,
    距离黄线_pct  REAL,
    FOREIGN KEY (scan_id) REFERENCES b1_scan(scan_id)
);
CREATE INDEX IF NOT EXISTS idx_b1c_code ON b1_candidate(code, scan_date);
CREATE INDEX IF NOT EXISTS idx_b1c_scan ON b1_candidate(scan_id);

CREATE TABLE IF NOT EXISTS b1_tracking (
    code          TEXT NOT NULL,
    date          TEXT NOT NULL,
    stage         TEXT DEFAULT 'watching', -- watching / near_b1 / b1 / observing / bought / holding / sell_candidate / sold / archived
    J             REAL,
    close         REAL,
    signals       TEXT,
    trend         TEXT,
    score         INTEGER,
    stage_days    INTEGER DEFAULT 0,      -- 当前stage持续天数
    action        TEXT,                   -- 关注 / 建仓 / 加仓 / 减仓 / 清仓 / 移出观察
    action_price  REAL,
    memo          TEXT,
    PRIMARY KEY (code, date)
);

-- ============================================================
-- 重点板块
-- ============================================================

CREATE TABLE IF NOT EXISTS focus_sector (
    name          TEXT PRIMARY KEY,
    sector_type   TEXT DEFAULT 'industry', -- industry / concept
    source        TEXT DEFAULT 'manual',   -- manual / scan_result
    priority      INTEGER DEFAULT 3,
    b1_density    REAL,                   -- B1数量/成分股数量
    notes         TEXT,
    tags          TEXT,                   -- JSON
    added_date    TEXT,
    last_scan_date TEXT,
    last_b1_count INTEGER,
    status        TEXT DEFAULT 'active'    -- active / archived
);

CREATE TABLE IF NOT EXISTS focus_sector_daily (
    date          TEXT NOT NULL,
    name          TEXT NOT NULL,
    change_pct    REAL,
    flow_in       REAL,                   -- 资金净流入（亿）
    leading_stock TEXT,
    b1_count      INTEGER,
    near_b1_count INTEGER,
    avg_score     REAL,
    hot_rank      INTEGER,
    PRIMARY KEY (date, name)
);

-- ============================================================
-- 审计日志
-- ============================================================

CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    table_name  TEXT NOT NULL,
    record_id   TEXT,
    action      TEXT NOT NULL,            -- INSERT / UPDATE / DELETE / ARCHIVE
    old_value   TEXT,                     -- JSON
    new_value   TEXT,                     -- JSON
    reason      TEXT,
    operator    TEXT DEFAULT 'system',    -- system / user
    created_at  TEXT
);

-- ============================================================
-- LLM 报告缓存
-- ============================================================

CREATE TABLE IF NOT EXISTS llm_report (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    code          TEXT,                     -- 股票代码（板块/持仓报告为空）
    report_type   TEXT NOT NULL,            -- stock / sector / holdings / watchlist / trade
    query_date    TEXT,
    prompt_hash   TEXT,                     -- input JSON hash，用于缓存去重
    raw_input     TEXT,                     -- JSON（输入数据摘要，max 8000）
    content       TEXT,                     -- LLM 生成的 Markdown
    model         TEXT,
    tokens_in     INTEGER DEFAULT 0,
    tokens_out    INTEGER DEFAULT 0,
    elapsed_sec   REAL,
    created_at    TEXT
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
        批量插入或更新。rows 格式: [{date, open, high, low, close, volume, amount, turnover, amplitude, change_pct}, ...]
        返回实际写入行数。
        """
        count = 0
        with self.conn:
            for r in rows:
                self.conn.execute(
                    """INSERT OR REPLACE INTO stock_daily (code, date, open, high, low, close, volume, amount, turnover, amplitude, change_pct)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (code, r["date"], r.get("open"), r.get("high"),
                     r.get("low"), r.get("close"), r.get("volume"),
                     r.get("amount"), r.get("turnover"), r.get("amplitude"), r.get("change_pct"))
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
            "SELECT date, open, high, low, close, volume, "
            "COALESCE(amount,0), COALESCE(turnover,0), COALESCE(amplitude,0), COALESCE(change_pct,0) "
            "FROM stock_daily WHERE code=? ORDER BY date DESC LIMIT ?",
            (code, limit)
        ).fetchall()
        # 按日期升序返回（B1 计算器需要）
        rows.reverse()
        return [
            {"date": r[0], "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": r[5],
             "amount": r[6], "turnover": r[7], "amplitude": r[8], "change_pct": r[9]}
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
            before = self.conn.total_changes
            with self.conn:
                for d in days:
                    self.conn.execute(
                        "INSERT OR IGNORE INTO trading_calendar (date) VALUES (?)", (d[:10],)
                    )
            added = self.conn.total_changes - before
            if added:
                print(f"  [calendar] 新增 {added} 个交易日 (共 {len(days)} 天)")
            return added

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
