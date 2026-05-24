"""
TC-6: 报告生成格式校验
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

from reporting.generator import generate_b1_report, generate_holdings_report
from scanning.sector_scanner import SectorOverviewResult, SectorB1Result, StockScanResult


def _make_stock(code, name, signals=None, J=50, score=2, trend="多头"):
    """辅助构造 StockScanResult"""
    s = StockScanResult(code=code, name=name, sector="电池")
    s.last = 25.0
    s.change_pct = 1.5
    s.J = J
    s.评分 = score
    s.趋势 = trend
    s.信号 = signals or []
    s.基础B1 = bool(signals)
    s.成交量 = 50000
    return s


def test_generate_b1_report_structure():
    """B1 报告必须包含 1/2/3 三个 section 和个股表格"""
    b1 = [
        _make_stock("002460", "赣锋锂业", signals=["拐头B"], J=12, score=4),
        _make_stock("300750", "宁德时代", signals=["超缩量B"], J=8, score=3),
    ]
    near = [
        _make_stock("000001", "平安银行", signals=[], J=18, score=2),
    ]
    overview = SectorOverviewResult(query="电池", sector_name="电池", sector_type="industry")
    overview.total_stocks = 3
    b1_result = SectorB1Result(name="电池")
    b1_result.stocks = b1 + near
    b1_result.b1_stocks = b1
    b1_result.near_b1_stocks = near

    combined = {
        "overview": overview,
        "b1": b1_result,
        "banned": [],
    }
    md = generate_b1_report(combined)
    assert "# 电池板块B1扫描" in md
    assert "## 1. 行业板块分析" in md
    assert "## 2. 板块个股分析" in md
    assert "## 3. 板块重点" in md
    assert "| 名称代码 | 主营业务 |" in md or "| 名称代码 | 主营业务 | 细分行业 |" in md


def test_generate_holdings_report_structure():
    """持仓报告包含总市值和浮动盈亏"""
    positions = [
        {"code": "002460", "name": "赣锋锂业", "avg_cost": 45.0, "total_qty": 1000, "strategy": "长线"},
    ]
    daily_data = {
        "002460": {"last": 48.0, "信号": ["拐头B"], "趋势": "多头", "J": 15},
    }
    md = generate_holdings_report(positions, daily_data)
    assert "# 持仓概览报告" in md
    assert "总市值" in md
    assert "浮动盈亏" in md
    assert "002460" in md
