"""
K线多源交叉验证 — 主源 vs 备源，逐日对比 OHLCV
用法:
    verifier = KlineVerifier()
    report = verifier.verify("002851", days=20)
    # report: {"match": True/False, "discrepancies": [...], "correlation": 0.99}
"""
from typing import Optional, List, Dict


class KlineVerifier:
    """双源交叉验证器"""

    def __init__(self):
        self._sources = []

        # 备选验证源（按优先级）
        try:
            from data_source.fetchers.akshare_fetcher import AkshareFetcher
            ak = AkshareFetcher()
            if ak.is_available():
                self._sources.append(("akshare", ak))
        except Exception:
            pass

        try:
            from data_source.fetchers.efinance_fetcher import EfinanceFetcher
            ef = EfinanceFetcher()
            if ef.is_available():
                self._sources.append(("efinance", ef))
        except Exception:
            pass

    @property
    def available(self) -> bool:
        return len(self._sources) > 0

    def verify(self, code: str, start_date: str, end_date: str,
               primary_candles: List[dict] = None) -> dict:
        """
        主源数据 vs 备源数据交叉验证。
        primary_candles: 主源已拉取的数据（如 iFind）。为 None 则从 DB 取。
        返回验证报告。
        """
        from storage.db import get_db

        # 1. 取主源数据
        if primary_candles is None:
            db = get_db()
            primary_candles = db.get_candles(code, 500)
            # 过滤日期范围
            primary_candles = [c for c in primary_candles if start_date <= c["date"] <= end_date]

        if not primary_candles:
            return {"match": None, "error": "主源无数据", "discrepancies": []}

        primary_map = {c["date"]: c for c in primary_candles}
        primary_dates = set(primary_map.keys())

        # 2. 逐源验证
        best_result = {"match": None, "source": None, "discrepancies": [], "correlation": None}

        for src_name, src in self._sources:
            try:
                candles = src.get_kline(code, start_date, end_date)
                if not candles or len(candles) < 5:
                    continue

                # 3. 对比
                secondary_map = {c["date"]: c for c in candles}
                common_dates = primary_dates & set(secondary_map.keys())

                if len(common_dates) < 5:
                    continue  # 共同日期太少，跳过

                disc = []
                close_diffs = []
                vol_ratios = []

                for d in sorted(common_dates):
                    p = primary_map[d]
                    s = secondary_map[d]
                    p_close = p.get("close", 0) or 0
                    s_close = s.get("close", 0) or 0
                    p_vol = p.get("volume", 0) or 1
                    s_vol = s.get("volume", 0) or 0

                    if p_close > 0:
                        close_diff = abs(p_close - s_close) / p_close * 100
                        close_diffs.append(close_diff)
                        if close_diff > 2:  # >2% 差异
                            disc.append({
                                "date": d,
                                "type": "close",
                                "primary": round(p_close, 2),
                                "secondary": round(s_close, 2),
                                "diff_pct": round(close_diff, 2),
                            })

                    if p_vol > 100:
                        vol_ratio = abs(p_vol - s_vol) / p_vol
                        vol_ratios.append(vol_ratio)
                        if vol_ratio > 0.5:  # >50% 量差异
                            disc.append({
                                "date": d,
                                "type": "volume",
                                "primary": int(p_vol),
                                "secondary": int(s_vol),
                                "diff_pct": round(vol_ratio * 100, 1),
                            })

                # 计算相关系数
                p_closes = [primary_map[d]["close"] for d in common_dates if primary_map[d].get("close")]
                s_closes = [secondary_map[d]["close"] for d in common_dates if secondary_map[d].get("close")]
                corr = _pearson(p_closes, s_closes) if len(p_closes) >= 5 else None

                match = len(disc) == 0
                result = {
                    "match": match,
                    "source": src_name,
                    "common_dates": len(common_dates),
                    "discrepancies": disc,
                    "correlation": round(corr, 4) if corr else None,
                    "avg_close_diff": round(sum(close_diffs) / len(close_diffs), 2) if close_diffs else 0,
                    "avg_vol_ratio": round(sum(vol_ratios) / len(vol_ratios), 2) if vol_ratios else 0,
                }
                # 保留最佳结果(差异最小的)
                if best_result["match"] is None or (
                    result["match"] and not best_result["match"]) or (
                    result["correlation"] and (best_result["correlation"] is None or
                    result["correlation"] > best_result["correlation"])):
                    best_result = result

            except Exception as e:
                continue

        # 补充主源覆盖信息
        best_result["primary_dates"] = len(primary_dates)
        best_result["primary_source"] = "sqlite/ifind"
        return best_result


def _pearson(x, y):
    """皮尔逊相关系数"""
    n = len(x)
    if n < 3:
        return None
    mean_x = sum(x) / n
    mean_y = sum(y) / n
    cov = sum((x[i] - mean_x) * (y[i] - mean_y) for i in range(n))
    std_x = (sum((xi - mean_x) ** 2 for xi in x)) ** 0.5
    std_y = (sum((yi - mean_y) ** 2 for yi in y)) ** 0.5
    if std_x == 0 or std_y == 0:
        return None
    return cov / (std_x * std_y)
