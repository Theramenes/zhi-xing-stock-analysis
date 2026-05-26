"""
K线预处理器 — 从 OHLCV 数据提取形态特征，供 LLM 分析
"""
from typing import List


def _avg(vals, n=None):
    if n:
        vals = vals[-n:]
    return sum(vals) / len(vals) if vals else 0


def preprocess_kline(candles: List[dict], indicators: dict = None,
                     lookback: int = 20) -> dict:
    """
    从 K 线数据提取结构化特征。
    candles: [{date, open, high, low, close, volume, turnover, ...}]
    indicators: b1_calculator 输出
    """
    n = min(lookback, len(candles))
    recent = candles[-n:]
    O = [c["open"] for c in recent]
    H = [c["high"] for c in recent]
    L = [c["low"] for c in recent]
    C = [c["close"] for c in recent]
    V = [c.get("volume", 0) or 0 for c in recent]
    T = [c.get("turnover", 0) or 0 for c in recent]

    result = {
        "period": f"{recent[0]['date']} ~ {recent[-1]['date']}",
        "n_days": n,
        "kline_table": _build_kline_table(recent),
        "patterns": _detect_patterns(O, H, L, C, V, T),
        "volume_analysis": _analyze_volume(V, T),
        "price_structure": _analyze_price(C, H, L),
        "ma_context": _build_ma_context(indicators),
        "b1_context": _build_b1_context(indicators),
    }
    return result


def _build_kline_table(candles):
    lines = []
    lines.append("日期       | 开盘   | 最高   | 最低   | 收盘   | 涨跌%  | 成交量(手) | 换手率% |")
    lines.append("-----------|--------|--------|--------|--------|--------|-----------|---------|")
    prev_close = None
    for c in candles:
        chg = ""
        if prev_close and prev_close > 0:
            chg = f"{(c['close'] - prev_close) / prev_close * 100:+.2f}"
        vol = c.get("volume", 0) or 0
        to = c.get("turnover", 0) or 0
        lines.append(
            f"{c['date']} | {c['open']:>6.2f} | {c['high']:>6.2f} | {c['low']:>6.2f} | "
            f"{c['close']:>6.2f} | {chg:>6} | {vol:>9.0f} | {to:>6.2f}"
        )
        prev_close = c["close"]
    return "\n".join(lines)


def _detect_patterns(O, H, L, C, V, T):
    patterns = []
    last = len(C) - 1
    body = abs(C[last] - O[last])
    upper = H[last] - max(C[last], O[last])
    lower = min(C[last], O[last]) - L[last]
    total_range = H[last] - L[last] if H[last] > L[last] else 0.01
    body_ratio = abs(C[last] - O[last]) / total_range

    # 当日形态
    if body_ratio < 0.1:
        patterns.append("十字星(多空平衡)")
    elif lower > body * 2:
        patterns.append("锤子线(长下影, 买方承接)")
    elif upper > body * 2:
        patterns.append("射击之星(长上影, 卖方压力)")
    if C[last] > O[last] and body_ratio > 0.6:
        patterns.append(f"实体阳线({body_ratio:.0%})")
    elif C[last] < O[last] and body_ratio > 0.6:
        patterns.append(f"实体阴线({body_ratio:.0%})")

    # 组合形态
    if last >= 2:
        # 吞没
        if C[last] > O[last] and C[last] > O[last-1] and O[last] < C[last-1] and body_ratio > 0.5:
            patterns.append("看涨吞没(今日阳线完全包住昨日阴线)")
        elif C[last] < O[last] and C[last] < O[last-1] and O[last] > C[last-1] and body_ratio > 0.5:
            patterns.append("看跌吞没(今日阴线完全包住昨日阳线)")

    # 连续形态
    if len(C) >= 6:
        last_5_close = C[-6:-1]
        if all(last_5_close[i] >= last_5_close[i+1] for i in range(4)):
            patterns.append("五连阴(持续下跌, 空方主导)")
        if all(last_5_close[i] <= last_5_close[i+1] for i in range(4)):
            patterns.append("五连阳(持续上涨, 多方主导)")

    # 量价配合
    if last >= 1 and V[last] > _avg(V[:-1], 5) * 1.5:
        if C[last] > C[last-1]:
            patterns.append("放量上涨(量价配合良好)")
        else:
            patterns.append("放量下跌(抛压增强)")
    if last >= 1 and V[last] < _avg(V[:-1], 10) * 0.5:
        patterns.append("地量(成交量极度萎缩, 变盘前兆)")

    # 突破/跌破
    if last >= 10:
        high_10 = max(H[-11:-1])
        low_10 = min(L[-11:-1])
        if C[last] > high_10:
            patterns.append("突破10日最高价(向上突破)")
        if C[last] < low_10:
            patterns.append("跌破10日最低价(向下破位)")

    return patterns


def _analyze_volume(V, T):
    v5 = _avg(V, 5)
    v10 = _avg(V, 10)
    latest_v = V[-1]
    latest_t = T[-1] if T else 0

    analysis = {
        "volume_5d_avg": round(v5),
        "volume_10d_avg": round(v10),
    }

    if v10 > 0:
        ratio = latest_v / v10
        if ratio > 2:
            analysis["status"] = f"异常放量({ratio:.1f}x)"
        elif ratio > 1.3:
            analysis["status"] = f"温和放量({ratio:.1f}x)"
        elif ratio < 0.3:
            analysis["status"] = f"地量({ratio:.1%})"
        elif ratio < 0.6:
            analysis["status"] = f"缩量({ratio:.1%})"
        else:
            analysis["status"] = "量能平稳"

    if latest_t > 0:
        analysis["latest_turnover"] = latest_t
        if latest_t > 10:
            analysis["turnover_note"] = "高换手(>10%)，筹码交换活跃"
        elif latest_t < 1:
            analysis["turnover_note"] = "低换手(<1%)，交投清淡"

    # 量能趋势
    if len(V) >= 6:
        v_recent_3 = _avg(V[-3:])
        v_prev_3 = _avg(V[-6:-3])
        if v_recent_3 > v_prev_3 * 1.3:
            analysis["trend"] = "放量趋势"
        elif v_recent_3 < v_prev_3 * 0.7:
            analysis["trend"] = "缩量趋势"
        else:
            analysis["trend"] = "量能稳定"

    return analysis


def _analyze_price(C, H, L):
    if len(C) < 10:
        return {}
    return {
        "latest": C[-1],
        "high_10d": max(H[-10:]),
        "low_10d": min(L[-10:]),
        "high_20d": max(H),
        "low_20d": min(L),
        "range_20d": f"{min(L):.2f} - {max(H):.2f}",
        "position_in_range": f"{(C[-1] - min(L)) / (max(H) - min(L)) * 100:.0f}%" if max(H) > min(L) else "0%",
        "change_5d": f"{(C[-1] - C[-6]) / C[-6] * 100:+.2f}%" if len(C) >= 6 else "?",
        "change_10d": f"{(C[-1] - C[-11]) / C[-11] * 100:+.2f}%" if len(C) >= 11 else "?",
    }


def _build_ma_context(ind):
    if not ind:
        return {}
    return {
        "白线(短期趋势)": ind.get("白线"),
        "黄线(中期趋势)": ind.get("黄线"),
        "BBI": ind.get("BBI"),
        "趋势": ind.get("趋势"),
        "白线方向": "↑" if ind.get("白线_rising") else "↓" if ind.get("白线_rising") == False else "?",
        "黄线方向": "↑" if ind.get("黄线_rising") else "↓" if ind.get("黄线_rising") == False else "?",
        "强趋势股": ind.get("强趋势股"),
        "做上涨趋势": ind.get("做上涨趋势"),
        "超牛股": ind.get("超牛股"),
        "转势": ind.get("转势"),
    }


def _build_b1_context(ind):
    if not ind:
        return {}
    return {
        "J值": ind.get("J"),
        "J方向": "↑" if ind.get("J_rising") else "↓" if ind.get("J_rising") == False else "?",
        "K": ind.get("K"), "D": ind.get("D"),
        "RSI": ind.get("RSI"),
        "评分": ind.get("评分"),
        "B1信号": ind.get("信号", []),
        "基础B1/B2/B3": f"{ind.get('基础B1','?')}/{ind.get('基础B2','?')}/{ind.get('基础B3','?')}",
        "缩量状态": "超缩量" if ind.get("超缩量") else ("适当缩量" if ind.get("适当缩量") else "否"),
        "单针下20": ind.get("单针下20"),
        "洗盘异动": ind.get("洗盘异动"),
        "死叉": ind.get("死叉"),
        "破线": ind.get("破线"),
    }
