"""
K 线 Fetcher 统一抽象基类

所有 Fetcher 只负责"拉取"，不负责日期计算。
start_date/end_date 由 KlineFetchCoordinator 通过交易日历统一计算后传入。
"""
from abc import ABC, abstractmethod
from typing import List, Optional


class BaseKlineFetcher(ABC):
    """所有 K 线数据源的统一抽象基类。

    每个 Fetcher:
      - start_date/end_date 由 Coordinator 统一计算，直接传进来
      - 不做交易日历反推，不做硬编码 count
      - 不处理补缺逻辑
    """

    name: str = "base"
    priority: int = 99

    @abstractmethod
    def is_available(self) -> bool:
        """检查此数据源是否可用"""
        ...

    @abstractmethod
    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """获取日K线数据。

        Args:
            code: 纯数字股票代码，如 "002693"
            start_date: "YYYY-MM-DD"，由 Coordinator 通过交易日历计算
            end_date: "YYYY-MM-DD"，由 Coordinator 通过交易日历计算

        Returns:
            candles: [{"date","open","high","low","close","volume",...}]
            失败或无数据返回 None
        """
        ...
