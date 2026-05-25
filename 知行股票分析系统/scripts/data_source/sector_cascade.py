"""
板块排名多源级联 — iFind → freeStockLine → akshare → efinance
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class SectorCascade:
    def __init__(self):
        self._fail_count = {}
        self._disabled = set()

    def _disable(self, name):
        self._fail_count[name] = self._fail_count.get(name, 0) + 1
        if self._fail_count[name] >= 3:
            self._disabled.add(name)

    def _ok(self, name):
        self._fail_count[name] = 0

    def get_sector_rankings(self, top_n: int = 10) -> dict:
        """返回 {"top": [{name, change_pct}], "bottom": [{name, change_pct}]}"""
        for name, fn in self._sources():
            if name in self._disabled:
                continue
            try:
                result = fn()
                if result and result.get("top"):
                    self._ok(name)
                    result["source"] = name
                    return result
                self._disable(name)
            except Exception:
                self._disable(name)
        return {"top": [], "bottom": [], "source": "none"}

    def _sources(self):
        yield from self._try_ifind()
        yield from self._try_efinance()
        yield from self._try_akshare()

    def _try_ifind(self):
        from data_source.ifind_client import IFindClient
        ifind = IFindClient()
        if not ifind.is_available():
            return
        def fn():
            payload = json.dumps({"searchstring": "行业板块涨跌幅排行", "searchtype": "plate"}, ensure_ascii=False)
            data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=30)
            if not data or not data.get("ok"):
                return None
            tables = data.get("data", {}).get("tables", [])
            if not tables:
                return None
            tb = tables[0].get("table", {})
            names = [str(n) for n in tb.get("板块名称", [])]
            changes = tb.get("涨跌幅", [])
            all_sectors = []
            for i in range(min(len(names), len(changes))):
                all_sectors.append({"name": names[i], "change_pct": _safe(changes[i]) if i < len(changes) else 0})
            top = sorted(all_sectors, key=lambda x: x["change_pct"] or 0, reverse=True)[:10]
            bottom = sorted(all_sectors, key=lambda x: x["change_pct"] or 0)[:10]
            return {"top": top, "bottom": bottom}
        yield ("ifind", fn)

    def _try_efinance(self):
        try:
            import efinance as ef
            def fn():
                df = ef.stock.get_realtime_quotes(["行业板块"])
                if df is None or df.empty:
                    return None
                df_sorted = df.sort_values("涨跌幅", ascending=False)
                top = [{"name": str(r["板块名称"]), "change_pct": _safe(r["涨跌幅"])}
                       for _, r in df_sorted.head(10).iterrows()]
                bottom = [{"name": str(r["板块名称"]), "change_pct": _safe(r["涨跌幅"])}
                          for _, r in df_sorted.tail(10).iterrows()]
                return {"top": top, "bottom": bottom}
            yield ("efinance", fn)
        except ImportError:
            pass

    def _try_akshare(self):
        try:
            import akshare as ak
            import time, random
            def fn():
                time.sleep(random.uniform(1, 3))
                df = ak.stock_board_industry_name_em()
                if df is None or df.empty:
                    return None
                df_sorted = df.sort_values("涨跌幅", ascending=False)
                top = [{"name": str(r["板块名称"]), "change_pct": _safe(r["涨跌幅"])}
                       for _, r in df_sorted.head(10).iterrows()]
                bottom = [{"name": str(r["板块名称"]), "change_pct": _safe(r["涨跌幅"])}
                          for _, r in df_sorted.tail(10).iterrows()]
                return {"top": top, "bottom": bottom}
            yield ("akshare", fn)
        except ImportError:
            pass


def _safe(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").replace("%", ""))
    except (ValueError, TypeError):
        return None
