"""Efinance K线 Fetcher — 免费、快速，对标 JusticePlutus EfinanceFetcher"""
import logging
from datetime import datetime
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    import efinance as ef
    _HAS_EFINANCE = True
except ImportError:
    _HAS_EFINANCE = False
    ef = None


class EfinanceFetcher:
    name = "efinance"
    priority = 1  # 仅次于 iFind(0)

    def is_available(self) -> bool:
        return _HAS_EFINANCE

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """获取日K线，返回标准 candles 格式 [{date, open, high, low, close, volume}]"""
        if not self.is_available():
            return None

        try:
            df = ef.stock.get_quote_history(code, beg=start_date, end=end_date, klt=101, fqt=1)
            if df is None or df.empty:
                return None

            candles = []
            for _, row in df.iterrows():
                vol = float(row.get('成交量', 0) or 0)
                candles.append({
                    "date": str(row.get('日期', ''))[:10],
                    "open": float(row.get('开盘', 0) or 0),
                    "high": float(row.get('最高', 0) or 0),
                    "low": float(row.get('最低', 0) or 0),
                    "close": float(row.get('收盘', 0) or 0),
                    "volume": vol / 100 if vol > 100000 else vol,  # 统一转手
                })
            return candles if candles else None

        except Exception as e:
            logger.debug(f"[{self.name}] {code} 获取失败: {e}")
            return None
