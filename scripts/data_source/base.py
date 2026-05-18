"""
数据源抽象基类 — 所有数据源实现此接口
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class Candle:
    """标准化K线"""
    date: str
    open: float
    high: float
    low: float
    close: float
    volume: float  # 统一为手（100股）
    amount: float = 0  # 成交额（可选）


@dataclass
class StockInfo:
    """标准化股票信息"""
    code: str
    name: str
    industry: str = ""
    change_pct: float = 0.0


@dataclass
class SectorInfo:
    """板块信息"""
    name: str
    code: str = ""
    member_count: int = 0
    change_pct: float = 0.0
    flow_in: float = 0.0  # 资金净流入（亿）


@dataclass
class DataRequest:
    """数据请求"""
    symbol: str
    days: int = 120
    period: str = "daily"
    adjust: str = "qfq"  # 前复权


@dataclass
class DataResponse:
    """数据响应"""
    ok: bool
    candles: List[Candle] = field(default_factory=list)
    error: str = ""
    source: str = ""  # 数据来源标识（ifind / free / local）
    raw: Optional[dict] = None  # 原始响应（调试用）


class DataSource(ABC):
    """数据源抽象基类"""

    name: str = "base"

    @abstractmethod
    def get_kline(self, req: DataRequest) -> DataResponse:
        """获取K线历史数据"""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """检查此数据源是否可用"""
        ...

    def get_realtime(self, symbol: str) -> Optional[dict]:
        """获取实时行情（可选实现）"""
        return None

    def get_sector_list(self, kind: str = "industry") -> List[SectorInfo]:
        """获取板块列表（可选实现）"""
        return []

    def get_sector_members(self, name: str) -> List[StockInfo]:
        """获取板块成分股（可选实现）"""
        return []

    def get_news(self, symbol: str = "", limit: int = 20) -> List[dict]:
        """获取新闻/公告（可选实现）"""
        return []

    def get_index(self) -> Optional[dict]:
        """获取大盘指数（可选实现）"""
        return None
