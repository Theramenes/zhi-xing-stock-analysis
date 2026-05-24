"""
TC-3/TC-4: 关注列表 + 持仓/交易流水 CRUD 测试
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

from storage.portfolio_db import (
    add_to_watchlist,
    list_watchlist,
    remove_from_watchlist,
    add_position,
    list_positions,
    add_transaction,
    list_transactions,
    get_pnl_summary,
)


def test_watchlist_crud(temp_db):
    """关注列表：增、查、移出"""
    # add
    r = add_to_watchlist("002460", "赣锋锂业", source="manual", reason="锂电池龙头", priority=1)
    assert r in (1, 2)

    # list active
    items = list_watchlist("active")
    codes = [i["code"] for i in items]
    assert "002460" in codes

    # remove (archived)
    remove_from_watchlist("002460", "测试移出")
    items = list_watchlist("archived")
    codes = [i["code"] for i in items]
    assert "002460" in codes


def test_position_and_transaction_cost(temp_db):
    """持仓 + 交易流水：加仓后成本价计算、卖出后盈亏计算"""
    # 首次建仓
    add_position("002460", "赣锋锂业", avg_cost=45.0, total_qty=1000)
    pos = list_positions()[0]
    assert pos["avg_cost"] == 45.0
    assert pos["total_qty"] == 1000

    # 加仓
    add_transaction("002460", "2026-05-20", "buy", 500, 46.0, reason="B1信号加仓")
    pos = list_positions()[0]
    expected_cost = round((45.0 * 1000 + 46.0 * 500) / 1500, 3)
    assert pos["total_qty"] == 1500
    assert abs(pos["avg_cost"] - expected_cost) < 0.01

    # 卖出部分
    add_transaction("002460", "2026-05-21", "sell", 300, 48.0, reason="止盈")
    pos = list_positions()[0]
    assert pos["total_qty"] == 1200

    # 验证流水
    txs = list_transactions("002460")
    sell_tx = [t for t in txs if t["direction"] == "sell"][0]
    expected_pnl = round((48.0 - expected_cost) * 300, 2)
    assert abs(sell_tx["pnl"] - expected_pnl) < 0.1


def test_pnl_summary(temp_db):
    """盈亏汇总"""
    add_position("002460", "赣锋锂业", avg_cost=45.0, total_qty=1000)
    add_transaction("002460", "2026-05-20", "sell", 500, 48.0)
    summary = get_pnl_summary(days=30)
    assert summary["trades"] >= 1
    assert summary["total_pnl"] > 0
