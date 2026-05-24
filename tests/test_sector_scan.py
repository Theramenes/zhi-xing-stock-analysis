"""
TC-2: 板块B1扫描 — mock 数据源，控制扫描量
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

import pytest
from scanning.sector_scanner import SectorB1Scanner


def _make_candles_for_signal(signal_type="normal"):
    """构造 120 日 K 线"""
    candles = []
    for i in range(120):
        if signal_type == "b1":
            # 持续大跌后缩量
            base = 50 - i * 0.40 if i < 90 else 14 + (i - 90) * 0.02
            vol = 100000 - i * 600 if i < 90 else 5000 + (i - 90) * 30
        elif signal_type == "near_b1":
            base = 20 - i * 0.10 if i < 80 else 12 + (i - 80) * 0.03
            vol = 60000 - i * 300 if i < 80 else 15000 + (i - 80) * 100
        else:
            base = 10 + i * 0.02
            vol = 30000
        candles.append({
            "date": f"2026-01-{(i%30)+1:02d}",
            "open": round(base, 2),
            "high": round(base+0.3, 2),
            "low": round(base-0.2, 2),
            "close": round(base+0.1, 2),
            "volume": max(vol, 3000),
        })
    return candles


def mock_ensure_candles(code, required_days=120):
    if code == "000001":
        return _make_candles_for_signal("normal")
    elif code == "000002":
        return _make_candles_for_signal("near_b1")
    else:
        return _make_candles_for_signal("b1")


def test_sector_b1_scan_mocked(monkeypatch, mock_ifind_sector_members):
    """mock 3 只票，验证分类逻辑能跑通"""
    monkeypatch.setattr(
        "storage.kline_filler.ensure_candles",
        mock_ensure_candles,
        raising=False,
    )
    class FakeIfind:
        def is_available(self): return True
        def get_sector_members(self, name):
            from data_source.base import StockInfo
            return [
                StockInfo(code="000001", name="平安银行"),
                StockInfo(code="000002", name="万科A"),
                StockInfo(code="000063", name="中兴通讯"),
            ]
        def _call(self, *args, **kwargs):
            return {"ok": True, "data": {"tables": []}}
    monkeypatch.setattr(
        "data_source.registry.registry.get_source",
        lambda name: FakeIfind() if name == "ifind" else None,
        raising=False,
    )
    scanner = SectorB1Scanner(workers=1)
    combined = scanner.scan("电池", days=120)

    b1 = combined.get("b1")
    assert b1 is not None
    assert len(b1.stocks) == 3, f"应扫描 3 只，实际 {len(b1.stocks)}"
    # 流程跑通即可，不要求精确分类
    total_classified = len(b1.b1_stocks) + len(b1.near_b1_stocks) + len(b1.trend_hold_stocks)
    assert total_classified > 0
