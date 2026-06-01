"""
东财 K 线直连 Fetcher — 绕过 efinance/akshare，直接用 requests HTTP 调 API
避免库内部重试/连接池与我们的防爬层冲突
"""
import logging
import time
from typing import Optional, List

import requests

logger = logging.getLogger(__name__)

EM_KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Referer": "https://quote.eastmoney.com/",
}


class EMDirectFetcher:
    """东财直连 K线 Fetcher"""

    name = "em_direct"
    priority = 1  # 仅次于 iFind

    def is_available(self) -> bool:
        return True

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """获取日K线。

        code: 纯数字，如 "002693"
        start_date/end_date: "YYYYMMDD"
        """
        try:
            # 确定 market: 0=深圳, 1=上海
            if code.startswith(("6", "9")):
                secid = f"1.{code}"
            else:
                secid = f"0.{code}"

            params = {
                "fields1": "f1,f2,f3,f4,f5,f6,f7,f8,f9,f10,f11,f12,f13",
                "fields2": "f51,f52,f53,f54,f55,f56,f57,f58,f59,f60,f61",
                "beg": start_date.replace("-", ""),
                "end": end_date.replace("-", ""),
                "rtntype": 6,
                "secid": secid,
                "klt": 101,   # 日线
                "fqt": 1,     # 前复权
            }

            resp = requests.get(EM_KLINE_URL, params=params, headers=HEADERS, timeout=15)
            if resp.status_code != 200:
                logger.debug(f"[{self.name}] {code} HTTP {resp.status_code}")
                return None

            data = resp.json()
            klines = data.get("data", {}).get("klines", [])
            if not klines:
                return None

            candles = []
            for line in klines:
                parts = line.split(",")
                if len(parts) < 10:
                    continue
                vol = float(parts[5] or 0)
                candles.append({
                    "date": parts[0],
                    "open": float(parts[1]),
                    "close": float(parts[2]),
                    "high": float(parts[3]),
                    "low": float(parts[4]),
                    "volume": vol / 100 if vol > 100000 else vol,
                    "amount": float(parts[6] or 0),
                    "amplitude": float(parts[7] or 0),
                    "change_pct": float(parts[8] or 0),
                    "turnover": float(parts[10] or 0),
                })
            return candles if candles else None

        except Exception as e:
            logger.debug(f"[{self.name}] {code} 获取失败: {e}")
            return None
