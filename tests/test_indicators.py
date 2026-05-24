"""
TC-1: 单股指标计算测试
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

from indicators.b1_calculator import compute_single


def test_compute_single_basic(mock_candles_120):
    """基础计算：返回结果包含关键字段"""
    result = compute_single("000001", mock_candles_120)
    assert "J" in result
    assert "RSI" in result
    assert "趋势" in result
    assert "白线" in result
    assert "黄线" in result
    assert "评分" in result


def test_compute_single_b1_signal(mock_candles_for_b1):
    """构造大跌+缩量走势，应触发超卖或超缩量相关信号"""
    result = compute_single("000001", mock_candles_for_b1)
    # 不要求精确 J<20，只要触发任一低位信号即可
    has_signal = len(result.get("信号", [])) > 0
    has_suo = result.get("超缩量", False)
    has_near = result.get("J", 999) < 20
    assert has_signal or has_suo or has_near, \
        f"应触发超缩量或信号或J<20，实际 信号={result.get('信号')} 超缩量={has_suo} J={result.get('J')}"
