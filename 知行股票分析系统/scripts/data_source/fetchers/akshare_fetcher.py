"""Akshare K线 Fetcher — 免费、数据全但较慢，含限速"""
import logging
import time
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    import akshare as ak
    _HAS_AKSHARE = True
except ImportError:
    _HAS_AKSHARE = False
    ak = None


class AkshareFetcher:
    name = "akshare"
    priority = 2  # 次于 efinance

    # 连续请求间最小间隔（秒）
    _last_call = 0
    _MIN_INTERVAL = 0.5

    @classmethod
    def _rate_limit(cls):
        now = time.time()
        gap = now - cls._last_call
        if gap < cls._MIN_INTERVAL:
            time.sleep(cls._MIN_INTERVAL - gap)
        cls._last_call = time.time()

    def is_available(self) -> bool:
        return _HAS_AKSHARE

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """获取日K线。用 akshare stock_zh_a_hist 接口。"""
        if not self.is_available():
            return None

        self._rate_limit()
        try:
            # 确定 market 后缀
            if code.startswith('6'):
                symbol = code
            else:
                symbol = code

            # akshare 的 period="daily" 需要调整日期格式为 YYYYMMDD
            start = start_date.replace('-', '')
            end = end_date.replace('-', '')

            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily",
                start_date=start, end_date=end, adjust="qfq"
            )
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
                    "volume": vol / 100 if vol > 100000 else vol,
                    "amount": float(row.get('成交额', 0) or 0),
                    "turnover": float(row.get('换手率', 0) or 0),
                    "amplitude": float(row.get('振幅', 0) or 0),
                    "change_pct": float(row.get('涨跌幅', 0) or 0),
                })
            return candles if candles else None

        except Exception as e:
            logger.debug(f"[{self.name}] {code} 获取失败: {e}")
            return None

    def get_sector_members(self, sector_name: str) -> Optional[List[dict]]:
        """获取板块成分股"""
        self._rate_limit()
        try:
            df = ak.stock_board_concept_cons_ths(symbol=sector_name)
            if df is None or df.empty:
                return None
            stocks = []
            for _, row in df.iterrows():
                stocks.append({
                    "code": str(row.get('代码', '')),
                    "name": str(row.get('名称', '')),
                })
            return stocks
        except Exception:
            return None
