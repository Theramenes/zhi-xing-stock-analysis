"""
缩爆B1 — 爆量+缩量模式的识别与追踪
D=前均量天数  S=缩量比例  V=爆量倍数  N=支撑阈值

算法三步：
Step1: 找到爆量日（量比>V，当日收阳，前D天涨幅<D）
Step2: 次日必须缩量（量比<S）且收跌，或量比<S但收涨>5%（直接算爆发）
Step3: 后续追踪：缩量回踩不破支撑=N天，直到再次爆量爆发或跌破支撑失效

输出格式兼容 b1_calculator.py 的返回结构，可被 scoring.py 消费
"""
import json
import statistics
from typing import Optional


def scan(code: str, name: str, candles: list,
         D: int = 5, S: float = 0.75, V: float = 3, N: float = 0.2) -> dict:
    """
    扫描单只股票是否出现缩爆B1模式。

    参数:
        code: 股票代码
        name: 股票名称
        candles: K线列表 [{date, open, high, low, close, volume}]
        D: 前均量天数
        S: 缩量比例 (0.75 = 次日量<爆量75%)
        V: 爆量倍数 (3 = 爆量>均量3倍)
        N: 支撑阈值 (0.2 = 支撑位=爆量开盘价+日涨幅*20%)
    """
    if not candles or len(candles) < D + 5:
        return {"ok": False, "name": name, "reason": "数据不足"}

    n = len(candles)
    lo = max(0, n - 20)
    hi = n - 3

    for idx in range(lo, hi):
        b = candles[idx]
        pre = candles[idx - 1]['close'] if idx > 0 else b['close']

        # 均量
        avg_v = statistics.mean([
            candles[idx - i]['volume'] for i in range(1, D + 1)
        ])
        vr = b['volume'] / avg_v if avg_v > 0 else 0

        # Step1: 爆量+收阳（close>open，真阳线）+前期不涨
        if b['close'] <= pre or vr < V:
            continue
        if b['close'] <= b['open']:
            continue  # 假阳线/阴线，不算爆量
        d_gain = (
            (candles[idx - 1]['close'] - candles[idx - D]['close'])
            / candles[idx - D]['close'] * 100
        )
        if d_gain > D:
            continue

        B_vol = b['volume']
        B_open = b['open']
        B_close = b['close']
        day_gain = (B_close - B_open) / B_open
        boom_chg = (B_close - pre) / pre * 100
        support = B_open * (1 + day_gain * N)

        # Step2: 次日验证 — 必须真正缩量（相对均量，不只看爆量日）
        d2 = candles[idx + 1]
        d2r = d2['volume'] / B_vol       # 相对爆量日缩量比
        d2r_avg = d2['volume'] / avg_v   # 相对均量比（关键：防"假缩量"）
        d2chg = (d2['close'] - B_close) / B_close

        # 次日必须：①相对爆量日缩量(d2r<S) ②相对均量不暴增(d2r_avg<V) ③收跌
        if d2r < S and d2chg < 0 and d2r_avg < V:
            pass  # 正常缩量模式
        else:
            continue  # 次日放量/收涨/假缩量，不成立

        # Step3: 追踪后续
        hold = 1
        min_v = d2r
        ok = True
        for j in range(idx + 2, n):
            dj = candles[j]
            vr_j = dj['volume'] / B_vol
            min_v = min(min_v, vr_j)

            if dj['close'] < support:
                ok = False
                break

            if vr_j >= S:
                chg_j = (dj['close'] - candles[j - 1]['close']) / candles[j - 1]['close']
                if chg_j >= 0.05:
                    return {
                        "ok": True, "code": code, "name": name,
                        "type": "缩爆B1_已爆发",
                        "date": b.get('date', ''),
                        "boom_open": B_open,
                        "boom_close": B_close,
                        "vr": round(vr, 1),
                        "chg_pct": round(boom_chg, 1),
                        "vol": int(B_vol),
                        "avg_v": int(avg_v),
                        "d2r_pct": round(d2r * 100, 1),
                        "d2chg_pct": round(d2chg * 100, 1),
                        "support": round(support, 2),
                        "hold_days": hold,
                        "min_v_pct": round(min_v * 100, 1),
                        "is_active": False,
                        "now": candles[-1]['close'],
                        "breakout_date": dj.get('date', ''),
                        "breakout_chg_pct": round(chg_j * 100, 1),
                    }
                ok = False
                break
            hold += 1

        if not ok:
            continue

        return {
            "ok": True, "code": code, "name": name,
            "type": "缩爆B1_观察中",
            "date": b.get('date', ''),
            "boom_open": B_open,
            "boom_close": B_close,
            "vr": round(vr, 1),
            "chg_pct": round(boom_chg, 1),
            "vol": int(B_vol),
            "avg_v": int(avg_v),
            "d2r_pct": round(d2r * 100, 1),
            "d2chg_pct": round(d2chg * 100, 1),
            "support": round(support, 2),
            "hold_days": hold,
            "min_v_pct": round(min_v * 100, 1),
            "is_active": hold >= 3,
            "now": candles[-1]['close'],
        }

    return {"ok": False, "name": name, "reason": "未匹配"}


def batch_scan(targets: list, candles_map: dict,
               D: int = 5, S: float = 0.75, V: float = 3, N: float = 0.2) -> list:
    """
    批量扫描缩爆B1。

    参数:
        targets: [(code, name), ...]
        candles_map: {code: [candles]}
    返回:
        [result, ...] 仅返回 ok=True 的结果，按 is_active 排序
    """
    results = []
    for code, name in targets:
        candles = candles_map.get(code)
        if not candles:
            continue
        r = scan(code, name, candles, D=D, S=S, V=V, N=N)
        if r.get("ok"):
            results.append(r)

    # 活跃的排前面
    results.sort(key=lambda x: (x.get("is_active", False), x.get("hold_days", 0)), reverse=True)
    return results
