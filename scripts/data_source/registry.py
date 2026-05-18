"""
数据源注册与降级链路
优先级: iFind > freeStockLine > agent-stock(local)
"""
from typing import Optional

from .base import DataSource, DataRequest, DataResponse, Candle
from .config import config
from .ifind_client import IFindClient
from .free_client import FreeClient
from .cached_adapter import CachedAdapter


class DataSourceRegistry:
    """数据源注册表，管理优先级和降级
    优先级: iFind > freeStockLine > 缓存兜底
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

    def get_kline(self, symbol: str, days: int = 120, force: str = None) -> DataResponse:
        """
        按优先级获取K线，自动降级。

        Args:
            symbol: 股票代码
            days: 数据天数
            force: 强制使用指定数据源（ifind/free/local），跳过优先级

        Returns:
            DataResponse with candles or error
        """
        req = DataRequest(symbol=symbol, days=days)

        # 用户覆盖：force 参数或环境变量
        override = force or (config.force_source if config.force_source != "auto" else None)
        if override and override in self._sources:
            src = self._sources[override]
            if src.is_available():
                resp = src.get_kline(req)
                if resp.ok:
                    return resp
                # 如果强制的源失败，且非 local，降级到 local
                print(f"  ⚠️ [{override}] 查询失败: {resp.error}，降级到本地源")

        # 正常优先级链路
        last_error = ""
        for name in self._priority:
            src = self._sources[name]
            if not src.is_available():
                continue
            resp = src.get_kline(req)
            if resp.ok and len(resp.candles) >= 30:
                return resp
            last_error = resp.error

        return DataResponse(
            ok=False,
            error=f"所有数据源均失败 (已尝试: {', '.join(self._priority)}). 最后错误: {last_error}",
            source="none"
        )

    def get_realtime(self, symbol: str) -> Optional[dict]:
        """获取实时行情（优先iFind）"""
        for name in self._priority:
            src = self._sources[name]
            result = src.get_realtime(symbol)
            if result:
                return result
        return None


# 全局单例
registry = DataSourceRegistry()
