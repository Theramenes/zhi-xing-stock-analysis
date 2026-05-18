"""
行业分析器 — 细分行业聚合 + 内部逻辑分析

功能:
1. 按同花顺三级行业分组
2. 计算每组: 近N日涨跌均幅、资金流向合计、涨跌停统计
3. 识别核心龙头 + 异动标的
4. 构建行业层级树（用于 AI 推理产业链关系）
"""
import collections
import os
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@dataclass
class StockOverview:
    """单只股票的板块概览数据"""
    code: str
    name: str
    industry_path: str  # "一级-二级-三级"
    biz: str = ""                 # 主营业务（主营产品名称 或 概念解析 或 三级行业名）
    change_pct: float = 0.0       # 当日涨跌幅
    change_5d: float = 0.0        # 近5日涨跌幅
    fund_flow: float = 0.0        # 资金净流入
    turnover: float = 0.0         # 换手率
    volume_ratio: float = 0.0     # 量比
    amplitude: float = 0.0        # 振幅
    leader_tag: str = ""          # 概念龙头标签
    market_type: str = ""         # 股票市场类型（主板/创业板/科创板）


@dataclass
class SubIndustry:
    """细分行业聚合"""
    name: str                      # 三级行业全路径 "一级-二级-三级"
    level: int = 3                 # 1/2/3
    stocks: List[StockOverview] = field(default_factory=list)
    avg_change: float = 0.0
    avg_change_5d: float = 0.0
    total_fund_flow: float = 0.0   # 亿
    up_count: int = 0
    down_count: int = 0
    limit_up_count: int = 0
    limit_down_count: int = 0
    leaders: List[str] = field(default_factory=list)
    anomaly_stocks: List[StockOverview] = field(default_factory=list)


class IndustryAnalyzer:
    """行业分析器"""

    LIMIT_UP_THRESHOLD = 9.5
    LIMIT_DOWN_THRESHOLD = -9.5
    ANOMALY_CHANGE_THRESHOLD = 5.0
    ANOMALY_VOLUME_RATIO = 3.0

    def analyze(self, stocks: List[StockOverview], target_level: int = 2) -> Dict[str, SubIndustry]:
        """
        按行业层级分组并聚合。

        Args:
            stocks: 股票概览列表
            target_level: 分组粒度，1=一级行业, 2=二级, 3=三级

        Returns:
            {sub_industry_name: SubIndustry}
        """
        groups = collections.OrderedDict()

        for s in stocks:
            key = self._extract_level(s.industry_path, target_level)
            if key not in groups:
                groups[key] = SubIndustry(name=key, level=target_level)
            groups[key].stocks.append(s)

        # 计算每组聚合指标
        for name, grp in groups.items():
            n = len(grp.stocks)
            if n == 0:
                continue

            grp.avg_change = sum(s.change_pct for s in grp.stocks) / n
            grp.avg_change_5d = sum(s.change_5d for s in grp.stocks if s.change_5d) / max(
                sum(1 for s in grp.stocks if s.change_5d), 1
            )
            grp.total_fund_flow = sum(s.fund_flow for s in grp.stocks) / 1e8  # 转为亿

            grp.up_count = sum(1 for s in grp.stocks if s.change_pct > 0)
            grp.down_count = sum(1 for s in grp.stocks if s.change_pct < 0)
            grp.limit_up_count = sum(1 for s in grp.stocks if s.change_pct >= self.LIMIT_UP_THRESHOLD)
            grp.limit_down_count = sum(1 for s in grp.stocks if s.change_pct <= self.LIMIT_DOWN_THRESHOLD)

            # 领导人
            grp.leaders = list(set(s.leader_tag for s in grp.stocks if s.leader_tag))
            # 异动标的
            grp.anomaly_stocks = [
                s for s in grp.stocks
                if abs(s.change_pct) >= self.ANOMALY_CHANGE_THRESHOLD
                or s.volume_ratio >= self.ANOMALY_VOLUME_RATIO
                or abs(s.fund_flow) >= 5e8  # 资金流>5亿
            ]

        return groups

    def build_tree(self, stocks: List[StockOverview]) -> dict:
        """构建行业层级树（用于 AI 推理产业链关系）"""
        tree = {}
        for s in stocks:
            parts = s.industry_path.split('-')
            current = tree
            for part in parts:
                part = part.strip()
                if part not in current:
                    current[part] = {}
                current = current[part]
        return tree

    def tree_to_mermaid(self, tree: dict, parent: str = "", depth: int = 0, max_depth: int = 2) -> str:
        """行业树 → mermaid 图"""
        if depth >= max_depth:
            return ""
        lines = []
        for name, children in tree.items():
            node_id = name.replace(' ', '_')
            if parent:
                lines.append(f"    {parent} --> {node_id}")
            lines.append(self.tree_to_mermaid(children, node_id, depth + 1, max_depth))
        return '\n'.join(lines)

    def describe_tree(self, tree: dict, indent: int = 0) -> str:
        """行业树 → 文本缩进描述"""
        lines = []
        for name, children in sorted(tree.items()):
            prefix = "  " * indent + ("├─ " if indent > 0 else "")
            count = self._count_leaves(children)
            lines.append(f"{prefix}{name}" + (f" ({count}子行业)" if count > 0 else ""))
            if isinstance(children, dict) and children:
                lines.append(self.describe_tree(children, indent + 1))
        return '\n'.join(lines)

    def _extract_level(self, path: str, level: int) -> str:
        parts = path.split('-')
        return '-'.join(p.strip() for p in parts[:level])

    def _count_leaves(self, d: dict) -> int:
        if not isinstance(d, dict) or not d:
            return 0
        return len(d)


def parse_stock_overview_from_ifind(table: dict, keys: list) -> List[StockOverview]:
    """
    从 iFind a_share_common_query 返回的 table 解析 StockOverview 列表。
    自动适配不同的字段名（iFind 返回中文列名，GBK解码后可直接匹配）。
    """
    stocks = []
    codes = table.get('股票代码', [])
    names = table.get('股票简称', [])
    industries = table.get('所属同花顺行业', table.get('同花顺行业', []))

    # 结构匹配：不依赖中文字符，只用 key 中的日期模式 + 数值范围识别
    import re as _re
    fund_col = []; change_5d_col = []; turnover_col = []
    vol_ratio_col = []; biz_col = []; leader_col = []; market_col = []; amplitude_col = []
    _ratio1 = []; _ratio2 = []; _ratio3 = []  # 小数值字段收集器

    for k in keys:
        v = table[k]
        if not v: continue
        key_has_range = bool(_re.search(r'\[\d{8}-\d{8}\]', k))
        key_has_date = bool(_re.search(r'\[\d{8}\]', k)) and not key_has_range
        s = v[0] if v else 0
        try: sf = float(s) if s is not None else 0.0
        except (ValueError, TypeError): sf = 0.0
        is_str = isinstance(s, str)

        if key_has_range and abs(sf) < 500:
            change_5d_col = v
        elif key_has_date and abs(sf) > 1e6:
            fund_col = v
        elif key_has_date and abs(sf) < 500:
            if _ratio1 == []: _ratio1 = v
            elif _ratio2 == []: _ratio2 = v
            elif _ratio3 == []: _ratio3 = v
        elif is_str and len(s) > 30:
            biz_col = v

    # ratio 字段去重: 换手率值较大(0.5-50), 量比值较小(0.2-5), 日涨跌幅(-10~10)
    r1_avg = sum(abs(float(str(x))) if x else 0 for x in _ratio1[:10]) / max(len(_ratio1[:10]), 1) if _ratio1 else 0
    r2_avg = sum(abs(float(str(x))) if x else 0 for x in _ratio2[:10]) / max(len(_ratio2[:10]), 1) if _ratio2 else 0
    # 较大的给换手率，较小的给量比
    if r1_avg >= r2_avg:
        turnover_col, vol_ratio_col = _ratio1, _ratio2
    else:
        turnover_col, vol_ratio_col = _ratio2, _ratio1
    # 日涨跌幅（第三个小数值，通常是最后一个，值为正负百分比）
    _chg = _ratio3 if _ratio3 else ([0] * len(turnover_col))
    change_col = _chg

    for i in range(len(codes)):
        code = str(codes[i]).split('.')[0] if i < len(codes) else ''
        name = str(names[i]) if i < len(names) else ''
        industry = str(industries[i]) if i < len(industries) else ''

        def _f(arr, idx, default=0.0):
            if idx < len(arr) and arr[idx] is not None:
                try:
                    return float(arr[idx])
                except (ValueError, TypeError):
                    return default
            return default

        biz_raw = str(biz_col[i]) if i < len(biz_col) and biz_col[i] else ''
        # 主营业务: 优先概念解析, 其次主营产品名称, 最后用三级行业名
        biz_final = biz_raw[:30] if biz_raw else industry.split('-')[-1] if industry else ''

        stocks.append(StockOverview(
            code=code, name=name, industry_path=industry, biz=biz_final,
            change_pct=_f(change_col, i),
            change_5d=_f(change_5d_col, i),
            fund_flow=_f(fund_col, i),
            turnover=_f(turnover_col, i),
            volume_ratio=_f(vol_ratio_col, i),
            amplitude=_f(amplitude_col, i),
            leader_tag=str(leader_col[i]) if i < len(leader_col) and leader_col[i] else '',
            market_type=str(market_col[i]) if i < len(market_col) and market_col[i] else '',
        ))
    return stocks
