"""
freeStockLine 免费数据源客户端
通过 subprocess 调用 stockline_cli.py，返回标准化 DataResponse
"""
import json
import subprocess
import os
from typing import List, Optional

from .base import DataSource, DataRequest, DataResponse, Candle, SectorInfo, StockInfo
from .config import config


class FreeClient(DataSource):
    """freeStockLine 免费数据源"""

    name = "free"

    def is_available(self) -> bool:
        if not config.free_cli:
            return False
        return os.path.exists(config.free_cli)

    def _call(self, *args, timeout: int = 25) -> Optional[dict]:
        import os as _os
        cmd = [config.free_python, config.free_cli] + list(args)
        env = _os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        try:
            r = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
            stdout = r.stdout.decode("utf-8", errors="replace").strip()
            if not stdout:
                return {"error": "empty response"}
            return json.loads(stdout)
        except subprocess.TimeoutExpired:
            return {"error": "timeout"}
        except json.JSONDecodeError:
            return {"error": "json decode failed"}
        except Exception as e:
            return {"error": str(e)}

    def get_kline(self, req: DataRequest) -> DataResponse:
        """获取K线: quote-history --symbol CODE --days N --period daily --adjust qfq"""
        data = self._call(
            "quote-history",
            "--symbol", req.symbol,
            "--days", str(req.days),
            "--period", req.period,
            "--adjust", req.adjust,
            timeout=25
        )

        if not data or not data.get("ok"):
            return DataResponse(
                ok=False,
                error=data.get("error", "freeStockLine返回失败") if data else "无响应",
                source=self.name
            )

        # freeStockLine 返回格式可能与 iFind 略有不同，统一解析
        candles_raw = []
        resp = data.get("data", {})
        if isinstance(resp, dict):
            candles_raw = resp.get("candles", resp.get("kline", []))
        elif isinstance(resp, list):
            candles_raw = resp

        if not candles_raw:
            return DataResponse(ok=False, error="freeStockLine返回空K线", source=self.name)

        candles = []
        for c in candles_raw:
            vol = c.get("volume", 0)
            # freeStockLine 一般返回股
            candles.append(Candle(
                date=str(c.get("date", c.get("time", ""))),
                open=float(c.get("open", 0)),
                high=float(c.get("high", 0)),
                low=float(c.get("low", 0)),
                close=float(c.get("close", 0)),
                volume=vol / 100 if abs(vol) > 100000 else abs(vol),
                amount=abs(vol) * 0 if vol else 0
            ))

        return DataResponse(ok=True, candles=candles, source=self.name, raw=data)

    def get_sector_list(self, kind: str = "industry") -> List[SectorInfo]:
        """sector --kind industry --action rank"""
        data = self._call("sector", "--kind", kind, "--action", "rank", "--limit", "50", timeout=30)
        if not data or not data.get("ok"):
            return []
        resp = data.get("data", {})
        items = resp.get("items", resp.get("list", []))
        if not isinstance(items, list):
            items = []
        return [
            SectorInfo(
                name=s.get("name", s.get("行业", s.get("板块名称", ""))),
                change_pct=float(s.get("changePct", s.get("涨跌幅(%)", s.get("change", 0))) or 0)
            )
            for s in items
        ]

    def get_sector_members(self, name: str, kind: str = "concept") -> List[StockInfo]:
        """sector --kind concept --action constituents --query NAME --limit 100"""
        data = self._call("sector", "--kind", kind, "--action", "constituents",
                          "--query", name, "--limit", "100", timeout=30)
        if not data or not data.get("ok"):
            return []
        resp = data.get("data", {})
        items = resp.get("items", [])
        if not isinstance(items, list):
            return []
        members = []
        for s in items:
            code = str(s.get("代码", s.get("code", "")))
            members.append(StockInfo(
                code=code.split(".")[0] if "." in code else code,
                name=str(s.get("名称", s.get("name", ""))),
                change_pct=float(s.get("涨跌幅(%)", s.get("changePercent", 0)) or 0)
            ))
        return members

    def get_news(self, symbol: str = "", limit: int = 20) -> List[dict]:
        """news --symbol CODE 或 announcement --symbol CODE"""
        if symbol:
            data = self._call("news", "--symbol", symbol, "--limit", str(limit), timeout=15)
        else:
            data = self._call("news", "--limit", str(limit), timeout=15)
        if not data or not data.get("ok"):
            return []
        return data.get("data", [])
