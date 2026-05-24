"""
数据源注册与降级链路
多源级联: iFind > Efinance > Akshare > FreeStockLine > Baostock > SQLite 缓存
"""
from typing import Optional

from .base import DataSource, DataRequest, DataResponse, Candle
from .config import config
from .ifind_client import IFindClient
from .free_client import FreeClient
from .cached_adapter import CachedAdapter


class DataSourceRegistry:
    """数据源注册表，管理优先级和降级

    K线通过 KlineCascade 走完整的多源级联链:
      iFind → Efinance → Akshare → FreeStockLine → Baostock → SQLite
    实时行情 / 板块列表仍走旧链路 (iFind → free → cache)
    """

    def __init__(self):
        self._sources = {}
        self._priority = []

        # 注册所有可用源（按优先级）
        if config.ifind_cli:
            ifind = IFindClient()
            self._sources["ifind"] = ifind
            if ifind.is_available():
                self._priority.append("ifind")

        if config.free_cli:
            free = FreeClient()
            self._sources["free"] = free
            if free.is_available():
                self._priority.append("free")

        # 本地缓存兜底
        cache = CachedAdapter()
        self._sources["cache"] = cache
        self._priority.append("cache")

    def get_source(self, name: str) -> Optional[DataSource]:
        return self._sources.get(name)

    @property
    def available_sources(self) -> list:
        return self._priority.copy()

    @property
    def all_cascade_sources(self) -> list:
        """返回包含级联中所有源的列表"""
        base = self._priority.copy()
        try:
            from data_source.kline_cascade import get_cascade
            extra = [s for s in get_cascade().available_sources if s not in base]
            return base + extra
        except Exception:
            return base

    def get_kline(self, symbol: str, days: int = 120, force: str = None) -> DataResponse:
        """
        按优先级获取K线，自动降级（通过 KlineCascade 多源级联）。

        Args:
            symbol: 股票代码
            days: 数据天数
            force: 强制使用指定数据源，跳过优先级
        """
        req = DataRequest(symbol=symbol, days=days)

        # 用户覆盖：force 参数或环境变量
        override = force or (config.force_source if config.force_source != "auto" else None)
        if override and override in self._sources:
            src = self._sources[override]
            if src.is_available():
                resp = src.get_kline(req)
                if resp.ok and len(resp.candles) >= 30:
                    return resp
                print(f"  ⚠️ [{override}] 查询失败，走多源级联…")

        # 走 KlineCascade 多源级联
        try:
            from data_source.kline_cascade import get_cascade
            cascade = get_cascade()
            candles, source = cascade.get_kline(symbol, days=days)
            if candles:
                return DataResponse(
                    ok=True,
                    candles=[Candle(date=c["date"], open=c["open"], high=c["high"],
                                    low=c["low"], close=c["close"], volume=c["volume"])
                             for c in candles],
                    source=source,
                )
        except Exception as e:
            print(f"  ⚠️ KlineCascade 异常: {e}，降级到本地源")

        # 全失败，本地缓存兜底
        cache = self._sources.get("cache")
        if cache:
            return cache.get_kline(req)

        return DataResponse(
            ok=False,
            error="所有数据源均失败（含多源级联）",
            source="none"
        )

    def get_realtime(self, symbol: str) -> Optional[dict]:
        """获取实时行情（优先iFind → free → akshare）"""
        for name in self._priority:
            src = self._sources[name]
            result = src.get_realtime(symbol)
            if result:
                return result
        return None


# 全局单例
registry = DataSourceRegistry()
