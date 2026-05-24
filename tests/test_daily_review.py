"""
TC-5: 日终追踪状态机转换测试
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

from tracking.state_machine import transition, apply_transition
from storage.portfolio_db import add_to_watchlist, update_b1_stage


def test_transition_b1_to_observing():
    """B1 消失后应进入 observing"""
    ind = {"J": 35, "信号": [], "趋势": "多头", "评分": 2}
    assert transition("b1", ind) == "observing"


def test_transition_watching_to_b1():
    """出现信号后应从 watching 进入 b1"""
    ind = {"J": 12, "信号": ["拐头B"], "趋势": "多头", "评分": 4}
    assert transition("watching", ind) == "b1"


def test_transition_watching_to_near_b1():
    """J<20 但无信号 → near_b1"""
    ind = {"J": 18, "信号": [], "趋势": "多头", "评分": 2}
    assert transition("watching", ind) == "near_b1"


def test_apply_transition_writes_db(temp_db):
    """apply_transition 应写入 b1_tracking 表"""
    add_to_watchlist("002460", "赣锋锂业")
    ind = {"J": 10, "信号": ["拐头B"], "趋势": "多头", "评分": 4, "last": 25.0}
    result = apply_transition("002460", ind)
    assert result["to"] == "b1"

    from storage.portfolio_db import get_b1_tracking
    rows = get_b1_tracking("002460")
    assert len(rows) >= 1
    assert rows[-1]["stage"] == "b1"
