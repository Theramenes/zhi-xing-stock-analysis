"""
实时行情多源级联 — iFind → freeStockLine → akshare(sina/tencent) → efinance
对标 JusticePlutus DataFetcherManager.get_realtime_quote()
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_source.ifind_client import IFindClient
from data_source.free_client import FreeClient


class RealtimeCascade:
    def __init__(self):
        self._fail_count = {}
        self._disabled = set()

    def _disable(self, name):
        self._fail_count[name] = self._fail_count.get(name, 0) + 1
        if self._fail_count[name] >= 3:
            self._disabled.add(name)

    def _ok(self, name):
        self._fail_count[name] = 0

    def get_quote(self, code: str) -> dict | None:
        for name, fn in self._sources():
            if name in self._disabled:
                continue
            try:
                result = fn(code)
                if result and result.get("price"):
                    self._ok(name)
                    result["source"] = name
                    return result
                self._disable(name)
            except Exception:
                self._disable(name)
        return None

    def _sources(self):
        yield from self._try_ifind()
        yield from self._try_free()
        yield from self._try_efinance()

    def _try_ifind(self):
        ifind = IFindClient()
        if ifind.is_available():
            def fn(code):
                try:
                    resp = ifind.get_realtime_ohlcv(code)
                    if not resp or not resp.candles:
                        return None
                    c = resp.candles[-1]
                    return {
                        "price": c.close,
                        "change_pct": c.change_pct if hasattr(c, "change_pct") else None,
                    }
                except Exception:
                    return None
            yield ("ifind", fn)

    def _try_free(self):
        free = FreeClient()
        if free.is_available():
            def fn(code):
                data = free.get_realtime(code)
                if data and data.get("price"):
                    return data
                return None
            yield ("free", fn)

    def _try_efinance(self):
        try:
            import efinance as ef
            def fn(code):
                df = ef.stock.get_realtime_quotes()
                if df is None or df.empty:
                    return None
                row = df[df["股票代码"] == code]
                if row.empty:
                    return None
                r = row.iloc[0]
                return {
                    "price": _safe(r.get("最新价")),
                    "change_pct": _safe(r.get("涨跌幅")),
                    "volume_ratio": _safe(r.get("量比")),
                    "turnover_rate": _safe(r.get("换手率")),
                    "pe": _safe(r.get("市盈率")),
                    "pb": _safe(r.get("市净率")),
                }
            yield ("efinance", fn)
        except ImportError:
            pass


def _get(tb, keys, idx):
    for k in keys:
        for col in tb:
            if k in str(col):
                vals = tb[col]
                if idx < len(vals):
                    return _safe(vals[idx])
    return None


def _safe(v):
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None
