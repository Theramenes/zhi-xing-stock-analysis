"""
腾讯 K 线直连 Fetcher — 对标 FreeStockLine _history_tencent
接口: web.ifzq.gtimg.cn/appstock/app/fqkline/get
免费、无 token、无严格频率限制，不会被封

拉取数量由 start_date/end_date 日历天数 × 1.6 反算，不硬编码。
"""
import logging
from datetime import datetime
from typing import Optional, List

import requests

logger = logging.getLogger(__name__)

TENCENT_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
    ),
    "Referer": "https://gu.qq.com/",
}


def _to_tencent_symbol(code: str) -> str:
    """纯数字 → 腾讯代码格式: sz002693 / sh600276"""
    if code.startswith(("6", "9")):
        return f"sh{code}"
    return f"sz{code}"


class TencentFetcher:
    """腾讯 K 线 Fetcher — 免费源最高优先级（无封禁风险）"""

    name = "tencent"
    priority = 1

    def is_available(self) -> bool:
        return True

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        """
        获取日K线（前复权 qfq）。

        code: 纯数字，如 "002693"
        start_date/end_date: 由级联管理器通过交易日历统一计算，各数据源共享。
        腾讯 API 不支持服务端日期过滤，拉取数量 = 日历天数 × 1.6，客户端过滤。
        """
        try:
            # 拉取量 = 日历天数，一笔不多。不够由上层往前补
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            count = max((e - s).days + 1, 1)

            provider = _to_tencent_symbol(code)
            param = f"{provider},day,,,{count},qfq"

            resp = requests.get(
                TENCENT_KLINE_URL,
                params={"param": param},
                headers=HEADERS,
                timeout=15,
            )
            resp.raise_for_status()
            payload = resp.json()

            node = payload.get("data", {}).get(provider, {})
            rows = node.get("qfqday") or node.get("day") or node.get("data") or []

            if not rows:
                return None

            candles = []
            for row in rows:
                if not isinstance(row, list) or len(row) < 6:
                    continue
                date_str = str(row[0])
                if date_str < start_date or date_str > end_date:
                    continue
                vol = float(row[5]) if row[5] else 0
                candles.append({
                    "date": date_str,
                    "open": float(row[1]),
                    "close": float(row[2]),
                    "high": float(row[3]),
                    "low": float(row[4]),
                    "volume": vol / 100 if vol > 100000 else vol,
                    "amount": float(row[6]) if len(row) > 6 and row[6] else 0,
                })

            return candles if candles else None

        except Exception as e:
            logger.debug(f"[{self.name}] {code} 获取失败: {e}")
            return None
