"""
iFind (同花顺) 数据源客户端 — 纯 HTTP API，无外部 CLI 依赖
通过直接调用 iFind REST API 获取数据，返回标准化 DataResponse
"""
import json
import os
from typing import List, Optional

from .base import DataSource, DataRequest, DataResponse, Candle, SectorInfo, StockInfo


class IFindClient(DataSource):
    """iFind 付费数据源（HTTP 直连，无 CLI 依赖）"""

    name = "ifind"

    # K线最小指标集（OHLCV 5个）
    KLINE_INDICATORS = [
        "ths_open_price_stock", "ths_high_price_stock",
        "ths_low_stock", "ths_close_price_stock", "ths_vol_stock"
    ]

    def is_available(self) -> bool:
        """检查是否有 iFind Token（文件或环境变量）"""
        token_path = os.path.expanduser("~/.openclaw/tonghuashun-ifind-skill/token_state.json")
        if os.path.exists(token_path):
            return True
        if os.environ.get("ZX_IFIND_REFRESH_TOKEN"):
            return True
        return False

    # ============================================================
    # 底层 HTTP 调用
    # ============================================================

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

        token = ""
        # 1. 环境变量优先
        token = os.environ.get("ZX_IFIND_ACCESS_TOKEN", "")
        # 2. 兼容旧版 token 文件
        if not token:
            token_path = os.path.expanduser("~/.openclaw/tonghuashun-ifind-skill/token_state.json")
            try:
                with open(token_path) as f:
                    token = json.load(f).get("access_token", "")
            except Exception:
                pass
        try:
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
        """获取K线（兼容旧接口，委托 Coordinator 算日期）"""
        from data_source.kline_coordinator import get_coordinator
        c = get_coordinator()
        end = datetime.now().strftime("%Y-%m-%d")
        start = c.compute_start_date(end, min(req.days, 120))
        return self._get_kline_best(req.symbol, start or "2025-01-01", end)

    def get_kline_range(self, symbol: str, start_date: str, end_date: str) -> DataResponse:
        """精确日期范围获取K线"""
        return self._get_kline_best(symbol, start_date, end_date)

    def _get_kline_best(self, symbol: str, start_date: str, end_date: str) -> DataResponse:
        """三源 fallback: ① date_sequence → ② snap_shot"""
        code = symbol if '.' in symbol else self._to_ifind_code(symbol)

        for name, method in [
            ("date_sequence", lambda: self._try_date_sequence(code, start_date, end_date)),
            ("snapshot", lambda: self._try_snapshot(code, start_date) if start_date == end_date else None),
        ]:
            resp = method()
            if resp and resp.ok and resp.candles:
                return resp
            if resp and not resp.ok:
                print(f"  [ifind] {name}: {resp.error[:60] if resp.error else 'no data'}")

        return DataResponse(ok=False, error="iFind HTTP 数据源均失败", source="none")

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
                volume=abs(vol) / 100 if (vol and abs(vol) > 100000) else (abs(vol) if vol else 0),
            ))
        return DataResponse(ok=True, candles=candles, source=f"{self.name}/ds")

    # ============================================================
    # ② snap_shot (THS_SS) — 日快照，盘中/盘后 OHLCV
    # ============================================================

    def _try_snapshot(self, code: str, date_str: str) -> Optional[DataResponse]:
        """
        日快照 THS_SS — 单日查询，starttime==endtime==15:00:00。
        THS_SS('300083.SZ','tradeDate;open;high;low;latest;volume','','2026-05-11 15:00:00','2026-05-11 15:00:00')
        """
        payload = {
            "codes": code,
            "indicators": "tradeDate;open;high;low;latest;volume",
            "starttime": f"{date_str} 15:00:00",
            "endtime": f"{date_str} 15:00:00",
        }
        data = self._http("https://ft.10jqka.com.cn/api/v1/snap_shot", payload)
        if not data or data.get("errorcode") != 0:
            return None

        tables = data.get("tables", [])
        if not tables:
            return None

        tb = tables[0].get("table", {})
        times = tables[0].get("time", [])
        if not times:
            return None

        opens = tb.get("open", [])
        highs = tb.get("high", [])
        lows = tb.get("low", [])
        closes = tb.get("latest", [])
        vols = tb.get("volume", [])

        candles = []
        for i in range(len(times)):
            vol = vols[i] if i < len(vols) else 0
            candles.append(Candle(
                date=str(times[i])[:10] if len(str(times[i])) > 10 else str(times[i]),
                open=opens[i] if i < len(opens) else 0,
                high=highs[i] if i < len(highs) else 0,
                low=lows[i] if i < len(lows) else 0,
                close=closes[i] if i < len(closes) else 0,
                volume=vol / 100 if abs(vol) > 100000 else abs(vol),
            ))
        return DataResponse(ok=True, candles=candles, source=f"{self.name}/snapshot")

    # ============================================================
    # ④ THS_RQ — 实时行情快照（当日盘中/盘后 OHLCV）
    # ============================================================

    def get_realtime_ohlcv(self, code: str) -> Optional[DataResponse]:
        """
        THS_RQ 实时行情 → 当日 OHLCV。
        指标用逗号分隔（与 quote-history 一致）。
        """
        payload = {
            "codes": code,
            "indicators": "open,high,low,latest,volume,changeRatio,preClose,turnoverRatio,volumeRatio",
        }
        data = self._http("/real_time_quotation", payload)
        if not data or data.get("errorcode") != 0:
            return None

        tables = data.get("tables", [])
        if not tables:
            return None

        tb = tables[0].get("table", {})
        times = tables[0].get("time", [])
        if not times:
            return None

        opens = tb.get("open", [])
        highs = tb.get("high", [])
        lows = tb.get("low", [])
        closes = tb.get("latest", [])
        vols = tb.get("volume", [])

        candles = []
        for i in range(len(times)):
            vol = vols[i] if i < len(vols) else 0
            date_str = str(times[i])[:10] if times else ''
            candles.append(Candle(
                date=date_str,
                open=opens[i] if i < len(opens) else 0,
                high=highs[i] if i < len(highs) else 0,
                low=lows[i] if i < len(lows) else 0,
                close=closes[i] if i < len(closes) else 0,
                volume=vol / 100 if abs(vol) > 100000 else abs(vol),
            ))
        return DataResponse(ok=True, candles=candles, source=f"{self.name}/thrsq")

    @staticmethod
    def _to_ifind_code(code: str) -> str:
        c = code.strip().upper().replace('.SH', '').replace('.SZ', '').replace('.BJ', '')
        if c.startswith(('600', '601', '603', '605', '688')): return f"{c}.SH"
        if c.startswith(('920', '8')): return f"{c}.BJ"
        return f"{c}.SZ"
