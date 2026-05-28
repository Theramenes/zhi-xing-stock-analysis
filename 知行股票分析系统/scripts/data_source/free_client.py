"""
免费数据源客户端 — 纯 Python 实现，无外部 CLI 依赖
通过 efinance / akshare 获取数据，返回标准化 DataResponse
"""
from typing import List, Optional

from .base import DataSource, DataRequest, DataResponse, Candle, SectorInfo, StockInfo


class FreeClient(DataSource):
    """免费数据源（efinance / akshare 内嵌，无 CLI 依赖）"""

    name = "free"

    def is_available(self) -> bool:
        """只要 efinance 或 akshare 有一个可用即可"""
        try:
            import efinance as ef  # noqa
            return True
        except ImportError:
            pass
        try:
            import akshare as ak  # noqa
            return True
        except ImportError:
            pass
        return False

    # ============================================================
    # K线获取
    # ============================================================

    def get_kline(self, req: DataRequest) -> DataResponse:
        """获取K线，优先 efinance，降级 akshare"""
        candles = self._try_efinance_kline(req)
        if candles:
            return DataResponse(ok=True, candles=candles, source=f"{self.name}/efinance")

        candles = self._try_akshare_kline(req)
        if candles:
            return DataResponse(ok=True, candles=candles, source=f"{self.name}/akshare")

        return DataResponse(ok=False, error="efinance / akshare 均无法获取K线", source=self.name)

    def _try_efinance_kline(self, req: DataRequest) -> Optional[List[Candle]]:
        try:
            import efinance as ef
        except ImportError:
            return None

        try:
            code = req.symbol.split('.')[0] if '.' in req.symbol else req.symbol
            df = ef.stock.get_quote_history(
                stock_codes=code,
                klt=101,  # 日线
                fqt=1 if req.adjust == "qfq" else 0,
            )
            if df is None or df.empty:
                return None

            # 限制条数
            if req.days and len(df) > req.days:
                df = df.tail(req.days)

            candles = []
            for _, row in df.iterrows():
                vol = row.get("成交量", 0)
                candles.append(Candle(
                    date=str(row.get("日期", row.get("date", ""))),
                    open=float(row.get("开盘", row.get("open", 0))),
                    high=float(row.get("最高", row.get("high", 0))),
                    low=float(row.get("最低", row.get("low", 0))),
                    close=float(row.get("收盘", row.get("close", 0))),
                    volume=float(vol) / 100 if abs(vol) > 100000 else abs(vol),
                    amount=float(row.get("成交额", row.get("amount", 0))),
                ))
            return candles
        except Exception as e:
            return None

    def _try_akshare_kline(self, req: DataRequest) -> Optional[List[Candle]]:
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            code = req.symbol.split('.')[0] if '.' in req.symbol else req.symbol
            df = ak.stock_zh_a_hist(
                symbol=code,
                period="daily",
                start_date="20200101",
                adjust="qfq" if req.adjust == "qfq" else "",
            )
            if df is None or df.empty:
                return None

            if req.days and len(df) > req.days:
                df = df.tail(req.days)

            candles = []
            for _, row in df.iterrows():
                vol = row.get("成交量", 0)
                candles.append(Candle(
                    date=str(row.get("日期", row.get("date", ""))),
                    open=float(row.get("开盘", row.get("open", 0))),
                    high=float(row.get("最高", row.get("high", 0))),
                    low=float(row.get("最低", row.get("low", 0))),
                    close=float(row.get("收盘", row.get("close", 0))),
                    volume=float(vol) / 100 if abs(vol) > 100000 else abs(vol),
                    amount=float(row.get("成交额", row.get("amount", 0))),
                ))
            return candles
        except Exception as e:
            return None

    # ============================================================
    # 板块数据
    # ============================================================

    def get_sector_list(self, kind: str = "industry") -> List[SectorInfo]:
        """板块排名，优先 efinance，降级 akshare"""
        result = self._try_efinance_sectors()
        if result:
            return result
        return self._try_akshare_sectors()

    def _try_efinance_sectors(self) -> Optional[List[SectorInfo]]:
        try:
            import efinance as ef
            df = ef.stock.get_realtime_quotes(["行业板块"])
            if df is None or df.empty:
                return None
            return [
                SectorInfo(
                    name=str(r.get("板块名称", "")),
                    change_pct=float(r.get("涨跌幅", 0)) if r.get("涨跌幅") else 0
                )
                for _, r in df.iterrows()
            ]
        except Exception:
            return None

    def _try_akshare_sectors(self) -> List[SectorInfo]:
        try:
            import akshare as ak
            df = ak.stock_board_industry_name_em()
            if df is None or df.empty:
                return []
            return [
                SectorInfo(
                    name=str(r.get("板块名称", "")),
                    change_pct=float(r.get("涨跌幅", 0)) if r.get("涨跌幅") else 0
                )
                for _, r in df.iterrows()
            ]
        except Exception:
            return []

    def get_sector_members(self, name: str, kind: str = "concept") -> List[StockInfo]:
        """板块成分股，优先 akshare，降级 efinance"""
        result = self._try_akshare_members(name)
        if result:
            return result
        return self._try_efinance_members(name)

    def _try_akshare_members(self, name: str) -> Optional[List[StockInfo]]:
        try:
            import akshare as ak
            # 行业板块成分股
            df = ak.stock_board_industry_cons_em(symbol=name)
            if df is None or df.empty:
                return None
            return [
                StockInfo(
                    code=str(r.get("代码", "")).split(".")[0],
                    name=str(r.get("名称", r.get("股票名称", "")))
                )
                for _, r in df.iterrows()
            ]
        except Exception:
            return None

    def _try_efinance_members(self, name: str) -> List[StockInfo]:
        try:
            import efinance as ef
            df = ef.stock.get_belong_board(name)
            if df is None or df.empty:
                return []
            # efinance 返回的格式可能不同，做通用处理
            members = []
            for _, r in df.iterrows():
                code = str(r.get("股票代码", r.get("code", ""))).split(".")[0]
                members.append(StockInfo(code=code, name=str(r.get("股票名称", r.get("name", "")))))
            return members
        except Exception:
            return []

    # ============================================================
    # 新闻
    # ============================================================

    def get_news(self, symbol: str = "", limit: int = 20) -> List[dict]:
        """个股新闻，通过 akshare 获取"""
        try:
            import akshare as ak
            code = symbol.split('.')[0] if '.' in symbol else symbol
            df = ak.stock_news_em(symbol=code)
            if df is None or df.empty:
                return []
            return [
                {
                    "title": str(r.get("新闻标题", "")),
                    "content": str(r.get("新闻内容", "")),
                    "time": str(r.get("发布时间", "")),
                }
                for _, r in df.head(limit).iterrows()
            ]
        except Exception:
            return []

    # ============================================================
    # 实时行情
    # ============================================================

    def get_realtime(self, symbol: str) -> Optional[dict]:
        """实时行情，优先 efinance"""
        try:
            import efinance as ef
            code = symbol.split('.')[0] if '.' in symbol else symbol
            df = ef.stock.get_realtime_quotes()
            if df is None or df.empty:
                return None
            row = df[df["股票代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "price": float(r.get("最新价", 0)),
                "change_pct": float(r.get("涨跌幅", 0)),
                "volume_ratio": float(r.get("量比", 0)) if r.get("量比") else None,
                "turnover_rate": float(r.get("换手率", 0)) if r.get("换手率") else None,
                "pe": float(r.get("市盈率-动态", 0)) if r.get("市盈率-动态") else None,
                "pb": float(r.get("市净率", 0)) if r.get("市净率") else None,
            }
        except Exception:
            pass

        # 降级 akshare
        try:
            import akshare as ak
            code = symbol.split('.')[0] if '.' in symbol else symbol
            df = ak.stock_zh_a_spot_em()
            if df is None or df.empty:
                return None
            row = df[df["代码"] == code]
            if row.empty:
                return None
            r = row.iloc[0]
            return {
                "price": float(r.get("最新价", 0)),
                "change_pct": float(r.get("涨跌幅", 0)),
            }
        except Exception:
            return None
