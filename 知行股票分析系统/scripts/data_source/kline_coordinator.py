"""
K 线获取协调者 — 统一日期计算、数据源编排、补缺逻辑

所有日期计算集中在这一处。Fetcher 只收 start_date/end_date，不做自己的推断。

用法:
    coordinator = KlineFetchCoordinator()
    candles, source = coordinator.fetch_kline("002693", required_trading_days=114)
"""
import time
from datetime import datetime, timedelta
from typing import List, Optional, Tuple, Dict

from storage.db import get_db


class KlineFetchCoordinator:
    """K 线获取协调者"""

    # 熔断/节流参数
    FUSE_THRESHOLD = 8
    FUSE_COOLDOWN_SEC = 60      # 1分钟冷却，不阻塞批量扫描
    BACKOFF_BASE = 1.0
    BACKOFF_MAX = 2
    GLOBAL_INTERVAL = 2.0       # 掘金终端无封禁风险，2秒足矣

    def __init__(self):
        self._sources: List[Tuple[str, object, int]] = []
        self._fail_count: Dict[str, int] = {}
        self._cooldown_until: Dict[str, float] = {}
        self._last_request: float = 0.0
        self._init_sources()

    # ================================================================
    # 公开入口
    # ================================================================

    def fetch_kline(self, code: str, required_trading_days: int = 114) -> Tuple[Optional[List[dict]], str]:
        """
        统一 K 线获取入口。返回 (candles, source_name)。

        流程:
          1. 确保交易日历最新 (三级降级)
          2. 计算起始日期: end 往前 required_trading_days 个交易日
          3. 按优先级尝试各数据源 (iFind 快速路径 + 免费源带熔断/节流)
          4. 若返回数据不足，迭代往前补缺 (最多 3 轮)
          5. 写入 SQLite，返回结果
        """
        db = get_db()
        db.ensure_trading_calendar()
        end_date = datetime.now().strftime("%Y-%m-%d")

        start_date = self.compute_start_date(end_date, required_trading_days)
        if not start_date:
            return None, "none"

        # 主拉取
        candles, source = self._cascade_fetch(code, start_date, end_date)

        # 补缺
        if candles and len(candles) < required_trading_days:
            candles = self._iterative_backfill(code, required_trading_days, candles, start_date, end_date)

        # 写入 SQLite
        if candles:
            try:
                db.upsert_candles(code, candles)
            except Exception:
                pass

        return candles, source

    def compute_start_date(self, end_date: str, trading_days_needed: int) -> Optional[str]:
        """从交易日历反推起始日期。end_date 往前 trading_days_needed 个交易日。"""
        db = get_db()
        db.ensure_trading_calendar(end=end_date)
        all_days = db.get_trading_days("2020-01-01", end_date)
        if len(all_days) >= trading_days_needed:
            return all_days[-trading_days_needed]
        # 交易日历不够，返回最早可用
        return all_days[0] if all_days else None

    # ================================================================
    # 数据源注册
    # ================================================================

    def _init_sources(self):
        """注册所有数据源（按优先级）。iFind 单独处理（不走熔断）。"""
        # iFind
        from data_source.ifind_client import IFindClient
        ifind = IFindClient()
        if ifind.is_available():
            self._sources.append(("ifind", ifind, 0))
        else:
            print("  [info] iFind HTTP 不可用，跳过")

        # 掘金 MyQuant（免费源最高优先，数据质量接近看盘软件）
        from data_source.fetchers.myquant_fetcher import MyQuantFetcher
        mq = MyQuantFetcher()
        if mq.is_available():
            self._sources.append(("myquant", mq, 1))
        else:
            print("  [info] 掘金不可用（终端未启动或Token未配置），跳过")

        # 腾讯直连
        from data_source.fetchers.tencent_fetcher import TencentFetcher
        self._sources.append(("tencent", TencentFetcher(), 2))

        # 东财直连
        from data_source.fetchers.em_direct_fetcher import EMDirectFetcher
        self._sources.append(("em_direct", EMDirectFetcher(), 2))

        # efinance
        from data_source.fetchers.efinance_fetcher import EfinanceFetcher
        efin = EfinanceFetcher()
        if efin.is_available():
            self._sources.append(("efinance", efin, 3))

        # akshare
        from data_source.fetchers.akshare_fetcher import AkshareFetcher
        ak = AkshareFetcher()
        if ak.is_available():
            self._sources.append(("akshare", ak, 4))

        # baostock
        from data_source.fetchers.baostock_fetcher import BaostockFetcher
        bs = BaostockFetcher()
        if bs.is_available():
            self._sources.append(("baostock", bs, 5))

        # 代理轮转（东财系源用，不配则不启用）
        self._rotating_get = None
        try:
            from data_source.proxy_rotator import create_rotating_get
            self._rotating_get = create_rotating_get()
            if self._rotating_get:
                print("  [INFO] 代理轮转已启用（东财系源）")
            else:
                print("  [info] 代理轮转未配置（东财系源走直连）")
        except Exception:
            pass

        print(f"  [INFO] 注册 {len(self._sources)} 个数据源 + SQLite 兜底")

    @property
    def available_sources(self) -> List[str]:
        return [s[0] for s in self._sources] + ["sqlite"]

    # ================================================================
    # 级联拉取
    # ================================================================

    # 东财系数据源（需要用代理轮转）
    _EASTMONEY_SOURCES = {"em_direct", "efinance", "akshare"}

    def _call_fetcher(self, name: str, src, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """调用 fetcher。东财系源注入代理轮转。"""
        if self._rotating_get and name in self._EASTMONEY_SOURCES:
            from unittest.mock import patch
            try:
                with patch('requests.get', new=self._rotating_get):
                    return src.get_kline(code, start_date, end_date)
            except Exception:
                return None
        return src.get_kline(code, start_date, end_date)

    def _cascade_fetch(self, code: str, start_date: str, end_date: str) -> Tuple[Optional[List[dict]], str]:
        """按优先级遍历数据源。iFind 快速路径不走熔断。"""
        # 1. SQLite 缓存 — 必须覆盖到 end_date 才算有效
        db = get_db()
        cached = db.get_candles(code, 500)
        if cached:
            cached_dates = {c["date"] for c in cached}
            cached_max = max(cached_dates) if cached_dates else ""
            if len(cached_dates) >= 30 and cached_max >= end_date:
                return cached, "sqlite"

        # 2. iFind 快速路径（无熔断/节流）
        for name, src, _ in self._sources:
            if name == "ifind":
                try:
                    print(f"  [{name}] 尝试 {code} ...", end=" ")
                    candles = self._fetch_ifind(src, code, start_date, end_date)
                    if candles and len(candles) >= 5:
                        print(f"[OK]{len(candles)}条")
                        return candles, name
                    print("[FAIL]")
                except Exception as e:
                    print(f"[FAIL]{type(e).__name__}")
                break  # iFind 只试一次

        # 3. 免费源链路（带熔断/节流/退避）
        now = time.time()
        for name, src, _ in self._sources:
            if name == "ifind":
                continue

            if self._is_fused(name, now):
                remain = int(self._cooldown_until[name] - now)
                print(f"  [{name}] 熔断中 {remain}s，跳过")
                continue

            self._throttle()
            try:
                print(f"  [{name}] 尝试 {code} {start_date}~{end_date}...", end=" ")
                candles = self._backoff(name, src, code, start_date, end_date)
                if candles and len(candles) >= 5:
                    print(f"[OK]{len(candles)}条")
                    self._record_success(name)
                    return candles, name
                print("[FAIL]空/不足")
                self._disable(name)
            except Exception as e:
                print(f"[FAIL]{type(e).__name__}: {str(e)[:60]}")
                self._disable(name)

        if cached:
            return cached, "sqlite"
        return None, "none"

    def _fetch_ifind(self, ifind, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """iFind 适配：get_kline_range → 标准 dict 列表"""
        symbol = code if '.' in code else ifind._to_ifind_code(code)
        resp = ifind.get_kline_range(symbol, start_date, end_date)
        if resp and resp.ok and resp.candles:
            return [
                {"date": c.date, "open": c.open, "high": c.high,
                 "low": c.low, "close": c.close, "volume": c.volume}
                for c in resp.candles
            ]
        return None

    # ================================================================
    # 迭代补缺
    # ================================================================

    def _iterative_backfill(self, code: str, required_days: int,
                            existing: List[dict], start: str, end: str) -> List[dict]:
        """数据不足时迭代往前补。缺<3天跳过（无意义补缺），新股直接放弃。"""
        gap = required_days - len(existing)
        if gap < 3:
            return existing  # 差1-2天不值得补，可能是停牌/上市日差
        db = get_db()
        all_days = db.get_trading_days("2020-01-01", datetime.now().strftime("%Y-%m-%d"))

        for _round in range(5):
            if len(existing) >= required_days:
                break
            earliest = min(c["date"] for c in existing)
            gap = required_days - len(existing)

            # 交易日历定位，退 gap 个交易日
            try:
                idx = all_days.index(earliest)
            except ValueError:
                idx = len(all_days) - 1

            if idx < max(gap, 5):
                # 新股：往前不够 gap 个交易日了
                print(f"  [backfill] {code} 新股/上市短(最早={earliest})，{len(existing)}天, 放弃")
                break

            # 精确补缺：最多拉按需+5天，避免东财系被炸断
            pull_gap = min(gap + 5, len(all_days) - 1)
            new_start = all_days[max(0, idx - pull_gap)]
            new_end = all_days[idx - 1]  # earliest 前一个交易日

            print(f"  [backfill] {code} 缺{gap}天, {new_start}~{new_end}")
            batch, _ = self._cascade_fetch(code, new_start, new_end)

            if batch and len(batch) > 0:
                existing_map = {c["date"]: c for c in existing}
                for c in batch:
                    if c["date"] not in existing_map:
                        existing_map[c["date"]] = c
                existing = sorted(existing_map.values(), key=lambda x: x["date"])
            else:
                # 这个日期段完全没数据（停牌），往前跳一段再试
                jump = idx - pull_gap
                if jump <= 0:
                    break
                # 更新 existing 的 earliest 到跳过的位置继续
                continue

        return existing

    # ================================================================
    # 防爬：熔断 + 节流 + 指数退避
    # ================================================================

    def _is_fused(self, name: str, now: float) -> bool:
        until = self._cooldown_until.get(name)
        return until is not None and now < until

    def _disable(self, name: str):
        self._fail_count[name] = self._fail_count.get(name, 0) + 1
        if self._fail_count[name] >= self.FUSE_THRESHOLD:
            self._cooldown_until[name] = time.time() + self.FUSE_COOLDOWN_SEC
            print(f"  [FUSE][{name}] 连续{self.FUSE_THRESHOLD}次失败，熔断{self.FUSE_COOLDOWN_SEC}s")

    def _record_success(self, name: str):
        self._fail_count[name] = 0
        self._cooldown_until.pop(name, None)

    def _throttle(self):
        elapsed = time.time() - self._last_request
        if elapsed < self.GLOBAL_INTERVAL:
            time.sleep(self.GLOBAL_INTERVAL - elapsed)
        self._last_request = time.time()

    def _backoff(self, name: str, src, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        for attempt in range(self.BACKOFF_MAX + 1):
            try:
                return self._call_fetcher(name, src, code, start_date, end_date)
            except Exception:
                if attempt < self.BACKOFF_MAX:
                    wait = self.BACKOFF_BASE * (2 ** attempt)
                    print(f"  [RETRY] #{attempt+1} {wait:.1f}s...", end=" ")
                    time.sleep(wait)
                else:
                    raise
        return None


# 全局单例
_coordinator: Optional[KlineFetchCoordinator] = None


def get_coordinator() -> KlineFetchCoordinator:
    global _coordinator
    if _coordinator is None:
        _coordinator = KlineFetchCoordinator()
    return _coordinator
