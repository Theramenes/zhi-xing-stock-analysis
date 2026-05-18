"""
本地缓存调试适配器
用于本地开发调试（没有 iFind/freeStockLine 可用时），读/写本地 JSON 缓存文件
"""
import json
import os
from typing import List

from .base import DataSource, DataRequest, DataResponse, Candle
from .config import config


class CachedAdapter(DataSource):
    """离线缓存适配器：仅读写本地 JSON 文件，不调用任何外部 API"""

    name = "cache"

    def __init__(self, cache_dir: str = None):
        self.cache_dir = cache_dir or os.path.join(config.workspace, "data", "scan_cache")

    def is_available(self) -> bool:
        return True

    def get_kline(self, req: DataRequest) -> DataResponse:
        """从本地缓存读取K线"""
        cache_file = os.path.join(self.cache_dir, f"{req.symbol}.json")
        if not os.path.exists(cache_file):
            return DataResponse(ok=False, error=f"缓存未命中 ({req.symbol}.json)", source=self.name)

        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            candles_raw = data if isinstance(data, list) else data.get("candles", data.get("data", []))
            if not candles_raw:
                return DataResponse(ok=False, error="缓存文件为空", source=self.name)

            candles = []
            for c in candles_raw[-req.days:]:
                candles.append(Candle(
                    date=str(c.get("date", c.get("time", ""))),
                    open=float(c.get("open", 0)),
                    high=float(c.get("high", 0)),
                    low=float(c.get("low", 0)),
                    close=float(c.get("close", 0)),
                    volume=float(abs(c.get("volume", 0))),
                ))
            return DataResponse(ok=True, candles=candles, source=self.name)
        except Exception as e:
            return DataResponse(ok=False, error=f"缓存读取失败: {e}", source=self.name)

    def save(self, symbol: str, candles: List[dict]):
        """保存K线到缓存文件"""
        os.makedirs(self.cache_dir, exist_ok=True)
        cache_file = os.path.join(self.cache_dir, f"{symbol}.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({"candles": candles}, f, ensure_ascii=False, indent=2)
