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
        """从 SQLite stock_daily 读取K线（替代旧 JSON scan_cache）"""
        try:
            from storage.db import get_db
            db = get_db()
            rows = db.get_candles(req.symbol, limit=req.days)
            if not rows:
                return DataResponse(ok=False, error=f"DB未命中 {req.symbol}", source=self.name)

            candles = []
            for r in rows:
                candles.append(Candle(
                    date=str(r.get("date", "")),
                    open=float(r.get("open", 0)),
                    high=float(r.get("high", 0)),
                    low=float(r.get("low", 0)),
                    close=float(r.get("close", 0)),
                    volume=float(abs(r.get("volume", 0))),
                ))
            return DataResponse(ok=True, candles=candles, source=self.name)
        except Exception as e:
            return DataResponse(ok=False, error=f"DB读取失败: {e}", source=self.name)

    def save(self, symbol: str, candles: List[dict]):
        """保存K线到 DB（替代旧 JSON scan_cache）"""
        try:
            from storage.db import get_db
            db = get_db()
            db.upsert_candles(symbol, candles)
        except Exception:
            pass
