"""
iFind (同花顺) 数据源客户端
通过 subprocess 调用 ifind_cli.py，返回标准化 DataResponse
"""
import json
import subprocess
import os
from typing import List, Optional

from .base import DataSource, DataRequest, DataResponse, Candle, SectorInfo, StockInfo
from .config import config


class IFindClient(DataSource):
    """iFind 付费数据源"""

    name = "ifind"

    # K线最小指标集（OHLCV 5个）
    KLINE_INDICATORS = [
        "ths_open_price_stock", "ths_high_price_stock",
        "ths_low_stock", "ths_close_price_stock", "ths_vol_stock"
    ]
    # 兼容旧 history 端点的指标名
    HISTORY_INDICATORS_SHORT = "open,high,low,close,volume"

    def is_available(self) -> bool:
        if not config.ifind_cli:
            return False
        return os.path.exists(config.ifind_cli)

    # ============================================================
    # 底层调用
    # ============================================================

    def _call(self, *args, timeout: int = 30) -> Optional[dict]:
        """通过 CLI subprocess 调用 ifind"""
        import os as _os
        cmd = [config.ifind_python, config.ifind_cli] + list(args)
        env = _os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
            stdout = r.stdout.decode("utf-8", errors="replace").strip()
            if not stdout:
                return {"error": "empty response", "stderr": (r.stderr or b"").decode("utf-8", errors="replace")[:200]}
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        except json.JSONDecodeError as e:
            return {"error": f"json decode: {e}"}
        except Exception as e:
            return {"error": str(e)}

    def _http(self, url_or_path: str, payload: dict = None, timeout: int = 15) -> Optional[dict]:
        """
        直接 HTTP 调用 iFind REST API。
        - 传 path: 拼到 https://quantapi.51ifind.com/api/v1 后面
        - 传完整 url: 直接用（如 snapshot 独立域名）
        """
        import requests
        if payload is None:
            return {"error": "no payload"}

        url = url_or_path if url_or_path.startswith("http") else \
              f"https://quantapi.51ifind.com/api/v1{url_or_path}"

        token_path = os.path.expanduser("~/.openclaw/tonghuashun-ifind-skill/token_state.json")
        try:
            with open(token_path) as f:
                token = json.load(f).get("access_token", "")
            resp = requests.post(
                url,
                headers={"Content-Type": "application/json", "access_token": token, "ifindlang": "cn"},
                json=payload, timeout=timeout
            )
            return resp.json()
        except Exception as e:
            return {"error": str(e)}

    # ============================================================
    # K线获取 — 优先级: date_sequence > cmd_history_quotation
    # ============================================================

    def get_kline(self, req: DataRequest) -> DataResponse:
        """获取K线（兼容旧接口，内部走双源 fallback）"""
        from datetime import datetime, timedelta
        end = datetime.now().strftime("%Y-%m-%d")
        start = (datetime.now() - timedelta(days=req.days * 2)).strftime("%Y-%m-%d")
        return self._get_kline_best(req.symbol, start, end)

    def get_kline_range(self, symbol: str, start_date: str, end_date: str) -> DataResponse:
        """精确日期范围获取K线"""
        return self._get_kline_best(symbol, start_date, end_date)

    def _get_kline_best(self, symbol: str, start_date: str, end_date: str) -> DataResponse:
        """四源 fallback: ① cmd_history → ② snap_shot → ③ date_sequence → ④ freeStockLine"""
        code = symbol if '.' in symbol else self._to_ifind_code(symbol)

        for name, method in [
            ("history", lambda: self._try_history(code, start_date, end_date)),
            ("snapshot", lambda: self._try_snapshot(code, start_date, end_date)),
            ("date_sequence", lambda: self._try_date_sequence(code, start_date, end_date)),
        ]:
            resp = method()
            if resp and resp.ok and resp.candles:
                return resp
            if resp and not resp.ok:
                print(f"  [ifind] {name}: {resp.error[:60] if resp.error else 'no data'}")

        # ④ freeStockLine 降级
        return self._try_freestock(code, start_date, end_date)

    def _try_date_sequence(self, code: str, start_date: str, end_date: str) -> Optional[DataResponse]:
        """date_sequence 取 K 线 — 优先方案"""
        payload = {
            "codes": code,
            "startdate": start_date,
            "enddate": end_date,
            "functionpara": {"Days": "Tradedays", "Fill": "Omit"},
            "indipara": [
                {"indicator": ind, "indiparams": ["", "", ""]}
                for ind in self.KLINE_INDICATORS
            ],
        }
        # 直接 HTTP（绕过 CLI 更快）
        data = self._http("/date_sequence", payload)
        if not data or data.get("errorcode") != 0:
            return None

        tables = data.get("tables", [])
        if not tables:
            return None

        tb = tables[0].get("table", {})
        times = tables[0].get("time", [])
        if not times:
            return DataResponse(ok=True, candles=[], source=f"{self.name}/ds")

        candles = []
        for i in range(len(times)):
            vol = tb.get("ths_vol_stock", [0]*len(times))[i]
            candles.append(Candle(
                date=str(times[i]),
                open=tb["ths_open_price_stock"][i],
                high=tb["ths_high_price_stock"][i],
                low=tb["ths_low_stock"][i],
                close=tb["ths_close_price_stock"][i],
                volume=vol / 100 if abs(vol) > 100000 else abs(vol),
            ))
        return DataResponse(ok=True, candles=candles, source=f"{self.name}/ds")

    def _try_history(self, code: str, start_date: str, end_date: str) -> Optional[DataResponse]:
        """cmd_history_quotation 取 K 线 — 降级方案，只要 OHLCV"""
        data = self._call(
            "quote-history",
            "--symbol", code.split('.')[0],
            "--start-date", start_date,
            "--end-date", end_date,
            timeout=30
        )
        if not data or not data.get("ok"):
            return None

        resp = data.get("data", {}).get("response", {})
        tables = resp.get("tables", [])
        if not tables:
            return None

        tb = tables[0].get("table", {})
        times = tables[0].get("time", [])
        if not times:
            return DataResponse(ok=True, candles=[], source=f"{self.name}/history")

        opens = tb.get("open", [])
        highs = tb.get("high", [])
        lows = tb.get("low", [])
        closes = tb.get("close", [])
        vols = tb.get("volume", [])

        candles = []
        for i in range(len(times)):
            vol = vols[i] if i < len(vols) else 0
            candles.append(Candle(
                date=str(times[i]),
                open=opens[i] if i < len(opens) else 0,
                high=highs[i] if i < len(highs) else 0,
                low=lows[i] if i < len(lows) else 0,
                close=closes[i] if i < len(closes) else 0,
                volume=vol / 100 if abs(vol) > 100000 else abs(vol),
            ))
        return DataResponse(ok=True, candles=candles, source=f"{self.name}/history")

    # ============================================================
    # ③ snap_shot (THS_SS) — 日快照，盘中/盘后 OHLCV
    # ============================================================

    def _try_snapshot(self, code: str, start_date: str, end_date: str) -> Optional[DataResponse]:
        """
        日快照 THS_SS — 只能单日查询，start == end，时间必须是 15:00:00。
        THS_SS('300083.SZ','tradeDate;open;high;low;latest;volume','','2026-05-11 15:00:00','2026-05-11 15:00:00')

        适合增量更新（缺1-2天时用），大批量缺数据时应走 date_sequence。
        """
        # 计算日期差：超过 5 天不用 snapshot（太多次 API 调用）
        from datetime import datetime, timedelta
        try:
            s = datetime.strptime(start_date, "%Y-%m-%d")
            e = datetime.strptime(end_date, "%Y-%m-%d")
            if (e - s).days > 5:
                return None  # 批量缺口，跳过 snapshot
        except ValueError:
            return None

        # 只取单日 snapshot
        all_candles = []
        current = s
        while current <= e:
            date_str = current.strftime("%Y-%m-%d")
            payload = {
                "codes": code,
                "indicators": "tradeDate;open;high;low;latest;volume",
                "starttime": f"{date_str} 15:00:00",
                "endtime": f"{date_str} 15:00:00",
            }
            data = self._http("https://ft.10jqka.com.cn/api/v1/snap_shot", payload)
            if data and data.get("errorcode") == 0:
                tables = data.get("tables", [])
                if tables:
                    tb = tables[0].get("table", {})
                    times = tables[0].get("time", [])
                    opens = tb.get("open", [])
                    highs = tb.get("high", [])
                    lows = tb.get("low", [])
                    closes = tb.get("latest", [])  # snapshot 用 latest
                    vols = tb.get("volume", [])
                    for i in range(len(times)):
                        vol = vols[i] if i < len(vols) else 0
                        all_candles.append(Candle(
                            date=str(times[i])[:10] if len(str(times[i])) > 10 else str(times[i]),
                            open=opens[i] if i < len(opens) else 0,
                            high=highs[i] if i < len(highs) else 0,
                            low=lows[i] if i < len(lows) else 0,
                            close=closes[i] if i < len(closes) else 0,
                            volume=vol / 100 if abs(vol) > 100000 else abs(vol),
                        ))
            current += timedelta(days=1)

        if all_candles:
            return DataResponse(ok=True, candles=all_candles, source=f"{self.name}/snapshot")
        return None

    # ============================================================
    # ④ freeStockLine — 免费源兜底
    # ============================================================

    def _try_freestock(self, code: str, start_date: str, end_date: str) -> DataResponse:
        """免费数据源降级"""
        from .registry import registry
        free = registry.get_source("free")
        if free and free.is_available():
            req = DataRequest(symbol=code.split('.')[0], days=120)
            return free.get_kline(req)
        return DataResponse(ok=False, error="所有数据源均失败", source="none")

    @staticmethod
    def _to_ifind_code(code: str) -> str:
        c = code.strip().upper().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
        if c.startswith(('600', '601', '603', '605', '688')): return f"{c}.SH"
        if c.startswith(('920', '8')): return f"{c}.BJ"
        return f"{c}.SZ"

    def get_sector_list(self, kind: str = "industry") -> List[SectorInfo]:
        """smart-query "A股行业板块涨跌幅排行" """
        data = self._call("smart-query", "--query", "A股行业板块涨跌幅排行", timeout=60)
        if not data or not data.get("ok"):
            return []

        resp = data.get("data", {}).get("response", {})
        tables = resp.get("tables", [{}])
        tb = tables[0].get("table", {})
        codes = tb.get("板块代码", [])
        names = tb.get("板块名称", [])
        changes = tb.get("涨跌幅", [])

        sectors = []
        for i in range(len(codes)):
            sectors.append(SectorInfo(
                code=str(codes[i]) if i < len(codes) else "",
                name=str(names[i]) if i < len(names) else "",
                change_pct=float(changes[i]) if i < len(changes) and changes[i] else 0
            ))
        return sectors

    def get_sector_members(self, name: str) -> List[StockInfo]:
        """
        获取板块成分股。使用 endpoint-call a_share_common_query，
        searchstring="{name}概念板块 成分股", searchtype="plate"
        """
        import json as _json
        payload = _json.dumps({
            "searchstring": f"{name}概念板块 成分股",
            "searchtype": "plate"
        }, ensure_ascii=False)
        data = self._call("endpoint-call", "--name", "a_share_common_query",
                          "--payload", payload, timeout=60)
        if not data or not data.get("ok"):
            # 降级：尝试 smart-query
            return self._get_members_via_smart_query(name)

        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return self._get_members_via_smart_query(name)

        tb = tables[0].get("table", {})
        codes = tb.get("股票代码", [])
        names = tb.get("股票简称", [])
        if not codes:
            return []

        members = []
        for i in range(len(codes)):
            code = str(codes[i]).split(".")[0] if i < len(codes) else ""
            name_str = str(names[i]) if i < len(names) else ""
            if code and name_str:
                members.append(StockInfo(code=code, name=name_str))
        return members

    def _get_members_via_smart_query(self, name: str) -> List[StockInfo]:
        """降级方案：smart-query"""
        data = self._call("smart-query", "--query", f"{name} 成分股 股票代码 股票名称", timeout=60)
        if not data or not data.get("ok"):
            return []

        resp = data.get("data", {}).get("response", {})
        tables = resp.get("tables", [])
        if not tables:
            return []

        tb = tables[0].get("table", {})
        codes = tb.get("股票代码", tb.get("code", []))
        names = tb.get("股票简称", tb.get("name", []))

        members = []
        for i in range(len(codes)):
            members.append(StockInfo(
                code=str(codes[i]).split(".")[0] if i < len(codes) else "",
                name=str(names[i]) if i < len(names) else ""
            ))
        return members

    def get_realtime(self, symbol: str) -> Optional[dict]:
        """quote-realtime --symbol CODE"""
        return self._call("quote-realtime", "--symbol", symbol, timeout=15)

    def get_dragon_tiger(self) -> Optional[dict]:
        """smart-query "龙虎榜" """
        return self._call("smart-query", "--query", "龙虎榜", timeout=30)
