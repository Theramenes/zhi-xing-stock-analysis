"""
板块扫描编排器 — 行业优先，概念降级

两个模式:
- SectorOverview: 板块概览（不扫个股），走行业查询 + 细分行业聚合
- SectorB1Scanner: 个股B1扫描，走行业/概念成分股 + K线 + B1计算

路由规则见 references/sector-routing.md
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import List, Optional, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from data_source.registry import registry as ds_registry
from data_source.base import DataRequest, StockInfo
from data_source.sector_registry import fuzzy_match_sectors
from indicators.b1_calculator import compute_single
from indicators.suo_bao_b1 import scan as suo_bao_scan
from .industry_analyzer import (
    IndustryAnalyzer, StockOverview, SubIndustry,
    parse_stock_overview_from_ifind,
)


@dataclass
class SectorOverviewResult:
    """板块概览结果"""
    query: str                          # 用户原始查询
    sector_name: str                    # iFind 查询用的行业名
    sector_type: str                    # "industry" / "concept"
    stocks: List[StockOverview] = field(default_factory=list)
    groups: Dict[str, SubIndustry] = field(default_factory=dict)
    industry_tree: dict = field(default_factory=dict)
    total_stocks: int = 0
    elapsed: float = 0


@dataclass
class StockScanResult:
    """单只股票的B1扫描结果"""
    code: str; name: str = ""; sector: str = ""; change_pct: float = 0.0
    last: float = 0; 白线: float = 0; 黄线: float = 0; BBI: float = 0
    J: float = 0; RSI: float = 0; K: float = 0; D: float = 0
    趋势: str = ""; 做上涨趋势: bool = False; 强趋势股: bool = False; 超牛股: bool = False
    评分: int = 0; 基础B1: bool = False; 基础B2: bool = False; 基础B3: bool = False
    信号: list = field(default_factory=list)
    单针下20: bool = False; 双线归零: bool = False
    短期K: float = 0; 长期K: float = 0
    缩量: bool = False; 适当缩量: bool = False; 超缩量: bool = False
    距离白线_pct: float = 0; 距离黄线_pct: float = 0
    当日振幅: float = 0; 近期振幅: float = 0; 远期振幅: float = 0
    洗盘异动: bool = False; 聚宝盆: bool = False; 双叉戟: bool = False
    大绿棒: bool = False
    下跌: bool = False; 放量下跌: bool = False; 死叉: bool = False; 破线: bool = False; 转势: bool = False
    suo_bao: Optional[dict] = None; error: str = ""

    def to_dict(self) -> dict:
        return {k: v for k, v in self.__dict__.items() if not k.startswith("_")}


@dataclass
class SectorB1Result:
    name: str; members: List[StockInfo] = field(default_factory=list)
    stocks: List[StockScanResult] = field(default_factory=list)
    b1_stocks: List[StockScanResult] = field(default_factory=list)
    near_b1_stocks: List[StockScanResult] = field(default_factory=list)
    trend_hold_stocks: List[StockScanResult] = field(default_factory=list)
    suo_bao_candidates: List[StockScanResult] = field(default_factory=list)
    errors: List[str] = field(default_factory=list); elapsed: float = 0


class SectorOverview:
    """板块概览 — 不扫个股，只看板块级别数据"""

    def __init__(self):
        self.analyzer = IndustryAnalyzer()

    def resolve(self, query: str) -> tuple:
        """
        解析用户查询 → (searchstring, sector_type)
        规则: 含"行业"/"板块"(不含"概念") → industry; 含"概念" → concept;
              含糊 → 默认 industry，提示用户
        """
        q = query.strip()
        has_industry = any(w in q for w in ['行业', '板块'])
        has_concept = '概念' in q

        if has_industry and not has_concept:
            return q.replace('行业', '').replace('板块', '').strip(), 'industry'
        if has_concept and not has_industry:
            return q.replace('概念', '').strip(), 'concept'
        if has_industry and has_concept:
            return q.replace('行业', '').replace('板块', '').replace('概念', '').strip(), 'industry'
        # 含糊 → 默认行业
        return q, 'industry'

    def scan(self, query: str) -> SectorOverviewResult:
        """执行板块概览扫描"""
        start = time.time()
        name, stype = self.resolve(query)
        result = SectorOverviewResult(query=query, sector_name=name, sector_type=stype)

        if stype == 'industry':
            self._scan_industry(name, result)
        else:
            self._scan_concept(name, result)

        result.elapsed = time.time() - start
        return result

    def _scan_industry(self, name: str, result: SectorOverviewResult):
        """行业概览查询"""
        ifind = ds_registry.get_source("ifind")
        if not ifind or not ifind.is_available():
            return

        # 主查询：全量股票 + 资金流 + 当日涨跌 + 近5日涨跌 + 换手 + 量比 + 主营业务
        searchstring = f"{name}行业 资金流向 涨跌幅 近5日涨跌 换手率 量比 主营产品名称"
        print(f"[Overview] iFind: {searchstring}")
        payload = json.dumps({"searchstring": searchstring, "searchtype": "stock"}, ensure_ascii=False)
        data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=60)
        if not data or not data.get("ok"):
            print(f"  iFind 查询失败")
            return

        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return
        tb = tables[0].get("table", {})
        keys = list(tb.keys())
        result.total_stocks = len(tb[keys[0]]) if keys else 0
        print(f"  {result.total_stocks} 只股票")

        # 解析
        stocks = parse_stock_overview_from_ifind(tb, keys)
        result.stocks = stocks

        # 行业树
        result.industry_tree = self.analyzer.build_tree(stocks)

        # 按三级行业分组
        result.groups = self.analyzer.analyze(stocks, target_level=3)

        # 补充龙头信息
        self._enrich_leaders(ifind, name, stocks)

    def _scan_concept(self, name: str, result: SectorOverviewResult):
        """概念概览 — 只取核心标的 + 标注所属行业"""
        ifind = ds_registry.get_source("ifind")
        if not ifind or not ifind.is_available():
            return

        # 概念查询：核心标的（龙头+异动），不加资金流避免截断
        searchstring = f"{name}概念 概念龙头 概念解析 涨跌幅 换手率 量比"
        print(f"[Overview-Concept] iFind: {searchstring}")
        payload = json.dumps({"searchstring": searchstring, "searchtype": "plate"}, ensure_ascii=False)
        data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=60)
        if not data or not data.get("ok"):
            return

        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return
        tb = tables[0].get("table", {})
        keys = list(tb.keys())
        result.total_stocks = len(tb[keys[0]]) if keys else 0
        print(f"  {result.total_stocks} 只（概念精选）")

        stocks = parse_stock_overview_from_ifind(tb, keys)
        result.stocks = stocks
        result.industry_tree = self.analyzer.build_tree(stocks)
        result.groups = self.analyzer.analyze(stocks, target_level=2)

    def _enrich_leaders(self, ifind, name: str, stocks: List[StockOverview]):
        """补充龙头信息（单独查询，避免截断主查询结果）"""
        try:
            payload = json.dumps({"searchstring": f"{name}行业 概念龙头", "searchtype": "stock"}, ensure_ascii=False)
            data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=30)
            if not data or not data.get("ok"):
                return
            tables = data.get("data", {}).get("tables", [])
            if not tables:
                return
            tb = tables[0].get("table", {})
            leader_codes = tb.get("股票代码", [])
            leader_tags = tb.get("概念龙头", [])
            leader_map = {}
            for i in range(min(len(leader_codes), len(leader_tags))):
                code = str(leader_codes[i]).split('.')[0]
                leader_map[code] = str(leader_tags[i]) if leader_tags[i] else ''

            for s in stocks:
                if s.code in leader_map and not s.leader_tag:
                    s.leader_tag = leader_map[s.code]
        except Exception:
            pass


class SectorB1Scanner:
    """板块B1扫描 — 先概览（行业数据）+ 再B1扫描个股 + 黑名单过滤"""

    def __init__(self, workers: int = 20, use_cache: bool = True):
        self.workers = workers
        # scan_cache JSON 已弃用，数据统一走 SQLite（stock_daily/watchlist_daily/b1_candidate）
        from config.blacklist import blacklist as bl
        self.blacklist = bl

    def scan(self, query: str, days: int = 120) -> dict:
        """
        板块B1扫描（含概览）：概览 → 黑名单过滤 → B1扫描 → 合并结果
        返回: {"overview": SectorOverviewResult, "b1": SectorB1Result, "banned": [...]}
        """
        # 1. 先拿概览
        ov = SectorOverview()
        name, stype = ov.resolve(query)
        print(f"[B1] 先拿概览: {query} → {name} ({stype})")
        overview_result = ov.scan(query)

        # 2. 拿成分股 + 黑名单过滤
        ifind = ds_registry.get_source("ifind")
        if not ifind or not ifind.is_available():
            return {"overview": overview_result, "b1": None, "banned": []}

        if stype == 'industry':
            searchstring = f"{name}行业"
        else:
            searchstring = f"{name}概念"

        members = self._get_members(ifind, searchstring)
        if not members:
            return {"overview": overview_result, "b1": None, "banned": []}

        print(f"  成分股: {len(members)} 只")
        kept, banned = self.blacklist.filter_stocks(members, "code", "name")
        if banned:
            print(f"  黑名单过滤: {len(banned)} 只 ({', '.join(str(s.code)+'('+s.name+')' for s in banned[:5])}{'...' if len(banned)>5 else ''})")
        print(f"  有效标的: {len(kept)} 只")

        # 3. B1扫描
        result = self._scan_stocks(kept, name, days)
        return {"overview": overview_result, "b1": result, "banned": [s.code for s in banned]}

    def _get_members(self, ifind, searchstring: str) -> List[StockInfo]:
        """获取成分股列表"""
        members = ifind.get_sector_members(searchstring)
        if not members:
            payload = json.dumps({"searchstring": f"{searchstring} 成分股 股票代码 股票简称", "searchtype": "stock"}, ensure_ascii=False)
            data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=60)
            if data and data.get("ok"):
                tables = data.get("data", {}).get("tables", [])
                if tables:
                    tb = tables[0].get("table", {})
                    codes = tb.get("股票代码", [])
                    names = tb.get("股票简称", [])
                    members = [StockInfo(code=str(codes[i]).split('.')[0], name=str(names[i]))
                               for i in range(min(len(codes), len(names)))]
        return members

    def _scan_stocks(self, members: List[StockInfo], sector_name: str, days: int) -> SectorB1Result:
        """对已过滤的股票列表执行 K线+B1扫描"""
        result = SectorB1Result(name=sector_name)
        result.members = members
        start = time.time()
        total = len(members)

        # 并行取K线
        print(f"[B1-2/5] iFind K线 ({self.workers}线程)...")
        kline_map = {}
        errors = []
        done = 0
        with ThreadPoolExecutor(max_workers=self.workers) as ex:
            futures = {ex.submit(self._fetch, m.code, days): m for m in members}
            for f in as_completed(futures):
                m = futures[f]; done += 1
                try:
                    c = f.result()
                    if c and len(c) >= 30:
                        kline_map[m.code] = c
                except Exception as e:
                    errors.append(f"{m.name}({m.code}): {e}")
                if done % 100 == 0 or done == total:
                    print(f"  {done}/{total} ({len(kline_map)} OK)", end="\r")
        print(f"  {done}/{total} ({len(kline_map)} OK)")

        # 批量B1
        print(f"[B1-3/5] 知行指标...")
        stocks = []
        for i, m in enumerate(members):
            candles = kline_map.get(m.code)
            if not candles: continue
            b1 = compute_single(m.code, candles)
            if "error" in b1: continue
            suo = suo_bao_scan(m.code, m.name, candles)
            sr = StockScanResult(
                code=m.code, name=m.name, sector=sector_name,
                last=b1.get("last", 0), 白线=b1.get("白线", 0), 黄线=b1.get("黄线", 0),
                BBI=b1.get("BBI", 0), J=b1.get("J", 0), RSI=b1.get("RSI", 0),
                K=b1.get("K", 0), D=b1.get("D", 0),
                趋势=b1.get("趋势", ""), 做上涨趋势=b1.get("做上涨趋势", False),
                强趋势股=b1.get("强趋势股", False), 超牛股=b1.get("超牛股", False),
                评分=b1.get("评分", 0), 基础B1=b1.get("基础B1", False),
                基础B2=b1.get("基础B2", False), 基础B3=b1.get("基础B3", False),
                信号=b1.get("信号", []), 单针下20=b1.get("单针下20", False),
                双线归零=b1.get("双线归零", False),
                短期K=b1.get("短期K", 0), 长期K=b1.get("长期K", 0),
                缩量=b1.get("缩量", False), 适当缩量=b1.get("适当缩量", False),
                超缩量=b1.get("超缩量", False),
                距离白线_pct=b1.get("距离白线_pct", 0),
                距离黄线_pct=b1.get("距离黄线_pct", 0),
                当日振幅=b1.get("当日振幅", 0), 近期振幅=b1.get("近期振幅", 0),
                远期振幅=b1.get("远期振幅", 0),
                洗盘异动=b1.get("洗盘异动", False),
                聚宝盆=b1.get("聚宝盆", False), 双叉戟=b1.get("双叉戟", False),
                大绿棒=b1.get("大绿棒", False),
                下跌=b1.get("下跌", False), 放量下跌=b1.get("放量下跌", False),
                死叉=b1.get("死叉", False), 破线=b1.get("破线", False),
                转势=b1.get("转势", False),
                suo_bao=suo if suo.get("ok") else None,
            )
            stocks.append(sr)
            if (i+1) % 100 == 0:
                print(f"  {i+1}/{len(members)}", end="\r")

        result.stocks = stocks
        print(f"  {len(stocks)} 完成")

        # 分类
        b1_list = [s for s in stocks if s.信号 or s.基础B1 or s.基础B2]
        b1_list.sort(key=lambda x: (len(x.信号), x.评分), reverse=True)
        near_list = [s for s in stocks if not (s.信号 or s.基础B1) and s.J < 20]
        near_list.sort(key=lambda x: x.J)
        hold_list = [s for s in stocks if s not in b1_list and s not in near_list and s.评分 >= 3 and s.趋势 == "多头"]
        hold_list.sort(key=lambda x: x.评分, reverse=True)
        suo_list = [s for s in stocks if s.suo_bao and s.suo_bao.get("is_active")]
        suo_list.sort(key=lambda x: x.suo_bao.get("hold_days", 0), reverse=True)

        result.b1_stocks = b1_list; result.near_b1_stocks = near_list
        result.trend_hold_stocks = hold_list; result.suo_bao_candidates = suo_list
        result.errors = errors; result.elapsed = time.time() - start
        print(f"[B1] B1:{len(b1_list)} 近B1:{len(near_list)} 趋势:{len(hold_list)} 缩爆:{len(suo_list)} [{result.elapsed:.0f}s]")
        return result

    def _fetch(self, code: str, days: int) -> Optional[list]:
        """获取K线：优先 SQLite → 不够则四源降级补缺 → 返回"""
        from storage.kline_filler import ensure_candles
        candles = ensure_candles(code, required_days=114)
        if candles and len(candles) >= 30:
            return candles
        # SQLite 兜底
        from storage.db import get_db
        return get_db().get_candles(code, days)
