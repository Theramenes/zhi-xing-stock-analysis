"""
K线多源级联管理器 — 向后兼容包装

日期计算、源编排、补缺逻辑已迁移到 KlineFetchCoordinator。
本类保留兼容接口，内部委托 Coordinator。
"""
import os
import sys
from typing import Optional, List, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

MAX_KLINE_DAYS = 125


def _now():
    from datetime import datetime
    return datetime.now().strftime("%Y-%m-%d")


class KlineCascade:
    """K 线多源级联管理器 — 向后兼容，委托 KlineFetchCoordinator"""

    def __init__(self):
        from data_source.kline_coordinator import get_coordinator
        self._coord = get_coordinator()

    @property
    def available_sources(self) -> List[str]:
        return self._coord.available_sources

    def source_status(self):
        return {}  # 简化，不暴露熔断状态

    def get_kline(self, code: str, days: int = None) -> Tuple[Optional[List[dict]], str]:
        """向后兼容：委托 KlineFetchCoordinator"""
        if days is None:
            days = MAX_KLINE_DAYS
        return self._coord.fetch_kline(code, required_trading_days=min(days, MAX_KLINE_DAYS))

    def get_kline_range(self, code: str, start_date: str, end_date: str) -> Tuple[Optional[List[dict]], str]:
        """向后兼容：直接按日期范围拉取"""
        return self._coord._cascade_fetch(code, start_date, end_date)


# 全局单例
_cascade: Optional[KlineCascade] = None


def get_cascade() -> KlineCascade:
    global _cascade
    if _cascade is None:
        _cascade = KlineCascade()
    return _cascade
