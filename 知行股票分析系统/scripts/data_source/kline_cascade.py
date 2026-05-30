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
    """K 线多源级联管理器 — JusticePlutus 级防爬：熔断器 + 指数退避 + 全局节流"""

    # 熔断参数
    FUSE_THRESHOLD = 3          # 连续失败几次触发熔断
    FUSE_COOLDOWN_SEC = 300     # 熔断后冷却多久（5分钟）
    BACKOFF_BASE = 1.0          # 指数退避基数（秒）
    BACKOFF_MAX = 3             # 最多重试几次
    GLOBAL_INTERVAL = 3.0       # 两次外部请求最小间隔（秒）

    def __init__(self):
        self._sources = []
        self._fail_count = {}      # 每个源的连续失败计数
        self._cooldown_until = {}  # 每个源的熔断截止时间戳
        self._last_request_time = 0.0  # 上次外部请求时间（全局节流）

        # 注册所有源（按优先级）
        ifind = IFindClient()
        if ifind.is_available():
            self._sources.append(("ifind", ifind, 0))
        else:
            print("  [info]iFind HTTP 不可用，跳过")

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
        now = time.time()
        for name, src, pri in self._sources:
            if self._is_fused(name, now):
                remain = int(self._cooldown_until[name] - now)
                status[name] = f"fused ({remain}s left)"
            elif hasattr(src, 'is_available'):
                status[name] = "ok" if src.is_available() else "unavailable"
            else:
                status[name] = "ok"
        status["sqlite"] = "ok" if self._sqlite_available else "unavailable"
        return status

    # ============================================================
    # 防爬：熔断器 + 指数退避 + 全局节流
    # ============================================================

    def _is_fused(self, name: str, now: float = None) -> bool:
        """检查源是否在熔断冷却期内"""
        if now is None:
            now = time.time()
        until = self._cooldown_until.get(name)
        return until is not None and now < until

    def _disable_source(self, name: str):
        """熔断：连续失败 N 次后冷却 M 分钟"""
        self._fail_count[name] = self._fail_count.get(name, 0) + 1
        if self._fail_count[name] >= self.FUSE_THRESHOLD:
            self._cooldown_until[name] = time.time() + self.FUSE_COOLDOWN_SEC
            print(f"  [FUSE][{name}] 连续{self.FUSE_THRESHOLD}次失败，熔断 {self.FUSE_COOLDOWN_SEC}s")

    def _record_success(self, name: str):
        """请求成功：重置失败计数并清除熔断"""
        self._fail_count[name] = 0
        self._cooldown_until.pop(name, None)

    def _global_throttle(self):
        """全局节流：确保两次外部请求之间至少间隔 GLOBAL_INTERVAL 秒"""
        elapsed = time.time() - self._last_request_time
        if elapsed < self.GLOBAL_INTERVAL:
            wait = self.GLOBAL_INTERVAL - elapsed
            time.sleep(wait)
        self._last_request_time = time.time()

    def _backoff_retry(self, name: str, fn, *args, **kwargs):
        """指数退避重试：失败间隔 1s → 2s → 4s，最多重试 BACKOFF_MAX 次"""
        for attempt in range(self.BACKOFF_MAX + 1):
            try:
                return fn(*args, **kwargs)
            except Exception as e:
                if attempt < self.BACKOFF_MAX:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    print(f"  [RETRY][{name}] #{attempt+1} 失败，{wait:.1f}s 后重试...")
                    time.sleep(wait)
                else:
                    raise
        return None

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
        """按日期范围获取 K 线。
        日期范围由级联管理器统一通过交易日历计算，所有数据源共享同一对 start_date/end_date。
        iFind（付费HTTP）走独立快速路径，不受熔断/节流/退避影响。
        免费源（efinance/akshare/baostock）共享熔断器 + 全局节流 + 指数退避。
        """
        from storage.db import get_db
        db = get_db()

        # 1. 先查 SQLite
        candles = db.get_candles(code, 500)
        if candles:
            existing_dates = {c["date"] for c in candles}
            if len(existing_dates) >= 30:
                return candles, "sqlite"

        # 2. iFind 快速路径（付费API，不需要防爬）
        for name, src, pri in self._sources:
            if name == "ifind":
                try:
                    print(f"  [{name}] 尝试获取 {code} {start_date}~{end_date}...", end=" ")
                    candles = self._try_ifind(code, start_date, end_date)
                    if candles and len(candles) >= 5:
                        print(f"[OK]{len(candles)}条")
                        db.upsert_candles(code, candles)
                        return candles, name
                    else:
                        print("[FAIL]空/不足")
                except Exception as e:
                    print(f"[FAIL]{type(e).__name__}: {str(e)[:60]}")
                break  # iFind 只试一次，失败就进免费源链路

        # 3. 免费源链路（带熔断 + 全局节流 + 指数退避）
        now = time.time()
        for name, src, pri in self._sources:
            if name == "ifind":
                continue  # iFind 已在上面处理过

            # 3a. 检查熔断
            if self._is_fused(name, now):
                remain = int(self._cooldown_until[name] - now)
                print(f"  [{name}] 熔断中，{remain}s 后恢复，跳过")
                continue

            # 3b. 全局节流
            self._global_throttle()

            try:
                print(f"  [{name}] 尝试获取 {code} {start_date}~{end_date}...", end=" ")

                # 3c. 指数退避重试
                candles = self._backoff_retry(name, src.get_kline, code, start_date, end_date)

                if candles and len(candles) >= 5:
                    print(f"[OK]{len(candles)}条")
                    self._record_success(name)
                    db.upsert_candles(code, candles)
                    return candles, name
                else:
                    print("[FAIL]空/不足")
                    self._disable_source(name)
            except Exception as e:
                print(f"[FAIL]{type(e).__name__}: {str(e)[:60]}")
                self._disable_source(name)

        # 4. 所有外部源失败，返回 SQLite 缓存
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
