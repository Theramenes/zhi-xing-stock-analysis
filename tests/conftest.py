"""
pytest 全局 fixtures
运行方式: pytest tests/ -v
"""
import json
import os
import sys
import tempfile

# 确保能导入项目代码
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

import pytest

from storage.db import StockDB


@pytest.fixture
def temp_db():
    """提供一个临时 SQLite 数据库，每次测试后自动清理"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    db = StockDB(path=path)
    yield db
    db.close()
    os.unlink(path)


@pytest.fixture
def mock_candles_120():
    """120 日 K 线 mock 数据（构造为一般震荡走势）"""
    candles = []
    base = 50.0
    for i in range(120):
        open_p = base + (i % 7) * 0.5 - 1.5
        high_p = open_p + 1.2
        low_p = open_p - 1.0
        close_p = open_p + (0.8 if i % 3 == 0 else -0.3)
        vol = 50000 + (i % 5) * 10000
        candles.append({
            "date": f"2026-01-{(i%30)+1:02d}",
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": vol,
        })
    return candles


@pytest.fixture
def mock_candles_for_b1():
    """
    构造一段会出现 '拐头B' 信号的 K 线：
    - 前 100 天持续大跌至低位（制造深度超卖）
    - 后 20 天极度缩量横盘（制造缩量+拐头）
    """
    candles = []
    for i in range(120):
        if i < 100:
            # 持续大跌，制造深度超卖
            base = 50 - i * 0.45
            vol = 100000 - i * 500
        else:
            # 低位极度缩量横盘
            base = 5 + (i - 100) * 0.01
            vol = 3000 + (i - 100) * 20
        open_p = base
        high_p = base + 0.1
        low_p = base - 0.1
        close_p = base + 0.02
        candles.append({
            "date": f"2026-01-{(i%30)+1:02d}",
            "open": round(open_p, 2),
            "high": round(high_p, 2),
            "low": round(low_p, 2),
            "close": round(close_p, 2),
            "volume": max(vol, 2000),
        })
    return candles


@pytest.fixture
def mock_ifind_sector_members(monkeypatch):
    """mock ifind_client.get_sector_members，返回 3 只小票"""
    def _mock(name: str):
        from data_source.base import StockInfo
        return [
            StockInfo(code="000001", name="平安银行"),
            StockInfo(code="000002", name="万科A"),
            StockInfo(code="000063", name="中兴通讯"),
        ]
    monkeypatch.setattr(
        "data_source.ifind_client.IFindClient.get_sector_members",
        _mock,
        raising=False,
    )
    return _mock
