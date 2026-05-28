"""
K线多源级联管理器 — 对标 JusticePlutus DataFetcherManager

级联链: iFind(HTTP) → Efinance → Akshare → Baostock → SQLite
用法:
    cascade = KlineCascade()
    candles, source = cascade.get_kline("002460", days=120)

每个源统一拉取上限 130 天（B1 计算需要 114 天，留 16 天缓冲）。
"""
import os
import sys
import time
from datetime import datetime, timedelta
from typing import Optional, List, Tuple, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_source.ifind_client import IFindClient
from data_source.fetchers.efinance_fetcher import EfinanceFetcher
from data_source.fetchers.akshare_fetcher import AkshareFetcher
from data_source.fetchers.baostock_fetcher import BaostockFetcher

# 所有源拉取K线的上限（B1 需要 114 天，多拉 6 天缓冲）
MAX_KLINE_DAYS = 120


def _now():
    return datetime.now().strftime("%Y-%m-%d")


class KlineCascade:
    """K 线多源级联管理器"""

    def __init__(self):
        self._sources = []
        self._fail_count = {}  # 每个源的连续失败计数
        self._disabled = set()

        # 注册所有源（按优先级）
        ifind = IFindClient()
        if ifind.is_available():
            self._sources.append(("ifind", ifind, 0))
        else:
            print("  [info]iFind CLI 路径不存在，跳过（token 过期或未安装）")

        efin = EfinanceFetcher()
        if efin.is_available():
            self._sources.append(("efinance", efin, 1))
        else:
            print("  [info]efinance 未安装，跳过")

        ak = AkshareFetcher()
        if ak.is_available():
            self._sources.append(("akshare", ak, 2))
        else:
            print("  [info]akshare 未安装，跳过")

        bs = BaostockFetcher()
        if bs.is_available():
            self._sources.append(("baostock", bs, 4))
        else:
            print("  [info]baostock 未安装，跳过")

        # SQLite 缓存（始终最后）
        self._sqlite_available = True
        print(f"  [INFO]已注册 {len(self._sources)} 个外部源 + SQLite 兜底")

    @property
    def available_sources(self) -> List[str]:
        return [s[0] for s in self._sources] + ["sqlite"]

    def source_status(self) -> Dict[str, str]:
        status = {}
        for name, src, pri in self._sources:
            if name in self._disabled:
                status[name] = "disabled (连续失败)"
            elif hasattr(src, 'is_available'):
                status[name] = "ok" if src.is_available() else "unavailable"
            else:
                status[name] = "ok"
        status["sqlite"] = "ok" if self._sqlite_available else "unavailable"
        return status

    def _disable_source(self, name: str):
        """熔断：连续失败3次后禁用"""
        self._fail_count[name] = self._fail_count.get(name, 0) + 1
        if self._fail_count[name] >= 3:
            self._disabled.add(name)
            print(f"  [FUSE][{name}] 连续3次失败，已熔断")

    def _record_success(self, name: str):
        if name in self._fail_count:
            self._fail_count[name] = 0

    def get_kline(self, code: str, days: int = None) -> Tuple[Optional[List[dict]], str]:
        """
        按优先级获取 K 线。返回 (candles, source_name)。
        用交易日历精确计算起始日期。
        """
        if days is None:
            days = MAX_KLINE_DAYS
        days = min(days, MAX_KLINE_DAYS)
        end = _now()
        start = self._trading_days_ago(end, days)
        return self.get_kline_range(code, start, end)

    @staticmethod
    def _trading_days_ago(end_date: str, n: int) -> str:
        """从 end_date 往前数 n 个交易日，返回起始日期"""
        from storage.db import get_db
        db = get_db()
        db.ensure_trading_calendar(end=end_date)
        all_days = db.get_trading_days("2020-01-01", end_date)
        if len(all_days) >= n:
            return all_days[-n]
        # fallback: 交易日历不足，用日历日估算
        return (datetime.strptime(end_date, "%Y-%m-%d") - timedelta(days=int(n * 1.5))).strftime("%Y-%m-%d")

    def get_kline_range(self, code: str, start_date: str, end_date: str) -> Tuple[Optional[List[dict]], str]:
        """按日期范围获取 K 线"""
        # 1. 先查 SQLite
        from storage.db import get_db
        db = get_db()
        candles = db.get_candles(code, 500)
        if candles:
            existing_dates = {c["date"] for c in candles}
            # 只要覆盖足够就不走外部源
            if len(existing_dates) >= 30:
                return candles, "sqlite"

        # 2. 按优先级走外部源
        for name, src, pri in self._sources:
            if name in self._disabled:
                continue
            try:
                print(f"  [{name}] 尝试获取 {code} {start_date}~{end_date}...", end=" ")
                if name == "ifind":
                    candles = self._try_ifind(code, start_date, end_date)
                else:
                    candles = src.get_kline(code, start_date, end_date)
                if candles and len(candles) >= 5:
                    print(f"[OK]{len(candles)}条")
                    self._record_success(name)
                    # 写入 SQLite
                    db.upsert_candles(code, candles)
                    return candles, name
                else:
                    print(f"[FAIL]空/不足")
                    self._disable_source(name)
            except Exception as e:
                print(f"[FAIL]{type(e).__name__}: {str(e)[:60]}")
                self._disable_source(name)

        # 3. 所有外部源失败，返回 SQLite 缓存
        if candles:
            return candles, "sqlite"
        return None, "none"

    def _try_ifind(self, code: str, start: str, end: str) -> Optional[List[dict]]:
        """尝试 iFind（含内部四级降级）"""
        ifind = IFindClient()
        resp = ifind.get_kline_range(code, start, end)
        if resp and resp.ok and resp.candles:
            return [
                {"date": c.date, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in resp.candles
            ]
        return None

# 全局单例
_cascade: Optional[KlineCascade] = None


def get_cascade() -> KlineCascade:
    global _cascade
    if _cascade is None:
        _cascade = KlineCascade()
    return _cascade
