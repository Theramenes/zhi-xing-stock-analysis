"""Baostock K线 Fetcher — 免费，需 login/logout"""
import logging
from typing import Optional, List

logger = logging.getLogger(__name__)

try:
    import baostock as bs
    _HAS_BAOSTOCK = True
except ImportError:
    _HAS_BAOSTOCK = False
    bs = None


class BaostockFetcher:
    name = "baostock"
    priority = 4  # 靠后，在 akshare/free 之后

    _logged_in = False

    def is_available(self) -> bool:
        return _HAS_BAOSTOCK

    def _ensure_login(self):
        if not self._logged_in and self.is_available():
            try:
                lg = bs.login()
                self._logged_in = (lg.error_code == '0')
            except Exception:
                self._logged_in = False
        return self._logged_in

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        if not self.is_available():
            return None
        if not self._ensure_login():
            return None

        # baostock 格式: sh.600519 或 sz.000001
        prefix = "sh" if code.startswith(('6', '9')) else "sz"
        bs_code = f"{prefix}.{code}"

        try:
            rs = bs.query_history_k_data_plus(
                bs_code,
                "date,open,high,low,close,volume",
                start_date=start_date, end_date=end_date,
                frequency="d", adjustflag="2"  # 前复权
            )
            if rs.error_code != '0':
                return None

            candles = []
            while rs.next():
                row = rs.get_row_data()
                vol = float(row[5] or 0)
                candles.append({
                    "date": row[0],
                    "open": float(row[1] or 0),
                    "high": float(row[2] or 0),
                    "low": float(row[3] or 0),
                    "close": float(row[4] or 0),
                    "volume": vol / 100 if vol > 100000 else vol,
                })
            return candles if candles else None

        except Exception as e:
            logger.debug(f"[{self.name}] {code} 获取失败: {e}")
            return None

    def __del__(self):
        if self._logged_in:
            try:
                bs.logout()
            except Exception:
                pass
