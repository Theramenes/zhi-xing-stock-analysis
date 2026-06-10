"""
实时行情多源级联 — 掘金→腾讯→akshare

用法:
    from data_source.quote_fetcher import QuoteFetcher
    q = QuoteFetcher()
    quote = q.get_quote("002693")  # 单只
    quotes = q.get_index_quotes()  # 主要指数
"""
import time
import random
from typing import Optional, Dict, List

TRACKED_INDEXES = {
    "000001": "上证综指",
    "399001": "深证成指",
    "399006": "创业板指",
    "000688": "科创50",
    "000300": "沪深300",
    "000016": "上证50",
    "399905": "中证500",
}

_TENCENT_INDEX_MAP = {
    "000001": "sh000001",
    "399001": "sz399001",
    "399006": "sz399006",
    "000688": "sh000688",
    "000300": "sh000300",
    "000016": "sh000016",
    "399905": "sz399905",
}


class QuoteFetcher:
    """实时行情获取"""

    def get_quote(self, code: str) -> Optional[Dict]:
        """单只个股行情。级联：掘金→腾讯→akshare。"""
        q = (
            self._try_myquant(code)
            or self._try_tencent(code)
            or self._try_akshare(code)
        )
        if q:
            n = q.get("name", "")
            if not n or "." in n or n == code:
                # 从 stock_info 缓存补名称
                try:
                    from storage.db import get_db
                    r = get_db().conn.execute("SELECT name FROM stock_info WHERE code=?", (code,)).fetchone()
                    if r and r[0]:
                        q["name"] = r[0]
                except Exception:
                    pass
        return q

    def get_quotes_batch(self, codes: List[str]) -> List[Dict]:
        """批量行情"""
        results = []
        for c in codes:
            q = self.get_quote(c)
            if q:
                results.append(q)
            time.sleep(random.uniform(0.3, 0.6))
        return results

    def get_index_quotes(self) -> List[Dict]:
        """主要指数行情。三级降级：掘金→腾讯→akshare"""
        results = []
        for code, name in TRACKED_INDEXES.items():
            q = None
            # 1. 掘金 (subprocess Python 3.10)
            q = self._try_myquant_index(code, name)
            # 2. 腾讯
            if not q:
                q = self._try_tencent_index(_TENCENT_INDEX_MAP.get(code, ""), code, name)
            # 3. akshare 降级
            if not q:
                q = self._try_akshare_index(code, name)
            if not q:
                q = {"code": code, "name": name, "price": 0, "change_pct": 0, "source": "none"}
            results.append(q)
            time.sleep(0.2)
        return results

    def _try_myquant_index(self, code: str, name: str) -> Optional[Dict]:
        try:
            import os, subprocess, json
            token = os.environ.get("ZX_MYQUANT_TOKEN", "")
            if not token:
                return None
            py_exe = None
            for c in [r"D:\Development\Python\python.exe", r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python313\python.exe"]:
                if os.path.exists(c):
                    py_exe = c
                    break
            if not py_exe:
                return None
            prefix = "SHSE" if code.startswith(("0","6","9")) else "SZSE"
            script = (
                "from gm.api import *\n"
                f"set_token('{token}')\n"
                "import json\n"
                f"data = current(symbols='{prefix}.{code}')\n"
                "if not data or len(data)==0: print('null')\n"
                "else:\n"
                " r=data[0]; out={'price':float(r.get('price',0)),'change_pct':float(r.get('change_pct',0) or r.get('change_ratio',0) or 0)}\n"
                " print(json.dumps(out))\n"
            )
            r = subprocess.run([py_exe, "-u", "-c", script], capture_output=True, text=True, timeout=15)
            if r.returncode != 0 or not r.stdout.strip() or r.stdout.strip() == "null":
                return None
            data = json.loads(r.stdout.strip())
            return {"code": code, "name": name, "price": data.get("price", 0),
                    "change_pct": data.get("change_pct", 0), "source": "myquant"}
        except Exception:
            return None

    def _try_akshare_index(self, code: str, name: str) -> Optional[Dict]:
        try:
            import akshare as ak
            df = ak.stock_zh_index_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {"code": code, "name": name,
                    "price": float(r.get("最新价", 0)),
                    "change_pct": float(r.get("涨跌幅", 0)),
                    "source": "akshare"}
        except Exception:
            return None

    # ============================================================
    # 掘金
    # ============================================================

    def _try_myquant(self, code: str) -> Optional[Dict]:
        """掘金 current() — subprocess 调用 Python 3.10"""
        import os, subprocess, json
        token = os.environ.get("ZX_MYQUANT_TOKEN", "")
        if not token:
            return None
        py310 = None
        for candidate in [
            r"D:\Development\Python\python.exe",
            r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python313\python.exe",
        ]:
            if os.path.exists(candidate):
                py310 = candidate
                break
        if not py310:
            return None
        prefix = "SHSE" if code.startswith(("5", "6", "9")) else "SZSE"
        script = (
            "import sys\n"
            "from gm.api import *\n"
            f"set_token('{token}')\n"
            "import json\n"
            f"data = current(symbols='{prefix}.{code}')\n"
            "if not data or len(data)==0: print('null',flush=True)\n"
            "else:\n"
            " r = data[0]\n"
            " # 掘金current字段名可能有差异，同时尝试多种key\n"
            " n = str(r.get('symbol','') or r.get('name','') or r.get('sec_name','') or '')\n"
            " p = float(r.get('price',0) or r.get('last_price',0) or r.get('trade',0) or 0)\n"
            " out = {'name':n,'price':p,"
            "'change_pct':float(r.get('change_pct',0) or r.get('change_ratio',0) or 0),"
            "'open':float(r.get('open',0)),'high':float(r.get('high',0)),"
            "'low':float(r.get('low',0)),'volume':float(r.get('volume',0) or 0),"
            "'amount':float(r.get('amount',0) or 0)}\n"
            " print(json.dumps(out,ensure_ascii=False),flush=True)\n"
        )
        try:
            r = subprocess.run([py310, "-u", "-c", script], capture_output=True, text=True, timeout=15)
            if r.returncode != 0 or not r.stdout.strip() or r.stdout.strip() == "null":
                return None
            data = json.loads(r.stdout.strip())
            data["code"] = code
            data["source"] = "myquant"
            return data
        except Exception:
            return None

    # ============================================================
    # 腾讯
    # ============================================================

    def _try_tencent(self, code: str) -> Optional[Dict]:
        try:
            import re, requests
            prefix = "sh" if code.startswith(("5", "6", "9")) else "sz"
            ts = f"{prefix}{code}"
            return self._try_tencent_index(ts, code, "")
        except Exception:
            return None

    def _try_tencent_index(self, ts: str, code: str, name: str) -> Optional[Dict]:
        try:
            import re, requests
            resp = requests.get(
                f"https://qt.gtimg.cn/q={ts}",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://gu.qq.com/"},
                timeout=8,
            )
            text = resp.text
            match = re.search(r'v_[a-z]{2}\d{5,6}="(.*)"', text)
            if not match:
                return None
            fields = match.group(1).split("~")
            if len(fields) < 35 or not fields[1]:
                return None
            return {
                "code": code,
                "name": fields[1],
                "price": float(fields[3]),
                "change_pct": float(fields[32]),
                "open": float(fields[5]),
                "high": float(fields[33]),
                "low": float(fields[34]),
                "volume": float(fields[6]),
                "amount": float(fields[37]) if len(fields) > 37 else 0,
                "pe": float(fields[39]) if fields[39] else None,
                "pb": float(fields[46]) if len(fields) > 46 and fields[46] else None,
                "volume_ratio": float(fields[49]) if len(fields) > 49 and fields[49] else None,
                "turnover_rate": float(fields[38]) if len(fields) > 38 and fields[38] else None,
                "total_mv": float(fields[44]) if len(fields) > 44 and fields[44] else None,
                "source": "tencent",
            }
        except Exception:
            return None

    # ============================================================
    # akshare 降级
    # ============================================================

    def _try_akshare(self, code: str) -> Optional[Dict]:
        try:
            import akshare as ak
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "code": code,
                "name": str(r.get("名称", "")),
                "price": float(r.get("最新价", 0)),
                "change_pct": float(r.get("涨跌幅", 0)),
                "open": float(r.get("今开", 0)),
                "high": float(r.get("最高", 0)),
                "low": float(r.get("最低", 0)),
                "volume": float(r.get("成交量", 0)),
                "amount": float(r.get("成交额", 0)),
                "pe": float(r.get("市盈率-动态", r.get("市盈率", 0))) if r.get("市盈率-动态") else None,
                "pb": float(r.get("市净率", 0)) if r.get("市净率") else None,
                "volume_ratio": float(r.get("量比", 0)) if r.get("量比") else None,
                "turnover_rate": float(r.get("换手率", 0)) if r.get("换手率") else None,
                "total_mv": float(r.get("总市值", 0)) if r.get("总市值") else None,
                "source": "akshare",
            }
        except Exception:
            return None
