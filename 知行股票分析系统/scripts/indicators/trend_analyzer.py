"""
知行趋势指标 — 黄白线独立分析，与 B1 平级

黄线 = (MA14+MA28+MA57+MA114)/4   — 中长期多空分水岭
白线 = EMA(EMA(C,10),10)          — 短期趋势
"""
from typing import List


def ema(arr, period):
    k = 2.0 / (period + 1)
    result = [arr[0]]
    for i in range(1, len(arr)):
        result.append(arr[i] * k + result[-1] * (1 - k))
    return result


def ma(arr, period):
    if len(arr) < period:
        return [None] * len(arr)
    result = [None] * (period - 1)
    for i in range(period - 1, len(arr)):
        result.append(sum(arr[i - period + 1:i + 1]) / period)
    return result


class TrendAnalyzer:
    def __init__(self, code, candles):
        self.code = code
        c = candles[-125:] if len(candles) >= 125 else candles
        self.C = [v['close'] for v in c]
        self.n = len(self.C)

        # 白线 = EMA(EMA(C,10),10)
        e10 = ema(self.C, 10)
        self.白 = ema(e10, 10)

        # 黄线 = (MA14+MA28+MA57+MA114)/4
        self.m14 = ma(self.C, 14)
        self.m28 = ma(self.C, 28)
        self.m57 = ma(self.C, 57)
        self.m114 = ma(self.C, 114)
        self.黄 = []
        for i in range(self.n):
            m_all = [self.m14[i], self.m28[i], self.m57[i], self.m114[i]]
            if any(x is None for x in m_all):
                self.黄.append(None)
            else:
                self.黄.append((self.m14[i] + self.m28[i] + self.m57[i] + self.m114[i]) / 4)

        # 取最后120个有效值
        self.白 = [v for v in self.白 if v is not None]
        self.黄 = [v for v in self.黄 if v is not None]
        min_len = min(len(self.白), len(self.黄))
        self.白 = self.白[-min_len:]
        self.黄 = self.黄[-min_len:]
        self.m = len(self.白)

    def compute(self, sensitivity: float = 1.0) -> dict:
        """sensitivity: 纠葛灵敏度, <1=更宽容穿越, >1=更严格"""
        if self.m < 10:
            return {"error": "数据不足", "code": self.code}

        w = self.白
        y = self.黄
        C = self.C[-self.m:] if hasattr(self, 'C') else []

        # ==========================================
        # 基础值
        # ==========================================
        diff = w[-1] - y[-1]                     # 正=白在上, 负=白在下
        diff_pct = diff / y[-1] * 100            # 带符号的差值%
        abs_diff_pct = abs(diff_pct)

        # ==========================================
        # 斜率 — 1日真实动量 + 5日趋势
        # ==========================================
        w_slope_1d = (w[-1] - w[-2]) / w[-2] * 100 if w[-2] else 0
        y_slope_1d = (y[-1] - y[-2]) / y[-2] * 100 if self.m >= 2 and y[-2] else 0
        w_slope_5d = (w[-1] - w[-6]) / w[-6] * 100 if self.m >= 6 and w[-6] else 0
        y_slope_5d = (y[-1] - y[-6]) / y[-6] * 100 if self.m >= 6 and y[-6] else 0
        _ys = y_slope_1d if abs(y_slope_1d) > 0.001 else 0
        slope_ratio = (w_slope_1d / _ys) if _ys else 0
        slope_ratio = max(-10, min(10, slope_ratio))  # cap at ±10

        # ==========================================
        # 差值趋势
        # ==========================================
        diff_prev = w[-2] - y[-2]
        gap_shrinking = abs(diff) < abs(diff_prev)  # 差值在缩小
        diff_growth = (abs(diff) - abs(diff_prev)) / abs(diff_prev) * 100 if abs(diff_prev) > 0 else 0

        # ==========================================
        # 穿越 — 用斜率验证, 不只看差值
        # ==========================================
        cross_now = (w[-1] > y[-1] and w[-2] <= y[-2])
        cross_death = (w[-1] < y[-1] and w[-2] >= y[-2])
        # 金叉有效: 白线上穿了, 且斜率验证 (不是贴线假穿)
        cross_valid = True
        if cross_now and abs_diff_pct < 0.5:
            # 差值<0.5%时, 只认斜率突出的穿越
            cross_valid = abs(slope_ratio) > 1.5 / sensitivity

        cross = None
        if cross_now:
            cross = "golden" if cross_valid else None
        elif cross_death:
            cross = "death" if abs_diff_pct > 0.3 else None

        cross_days = 0
        if not cross:
            for i in range(1, min(20, self.m - 1)):
                if w[-i] > y[-i] and w[-i - 1] <= y[-i - 1]:
                    cross_days = i
                    break

        # ==========================================
        # 涨穿黄线 — 白在黄下, 但收盘价突破黄线
        # ==========================================
        cross_yellow = False
        if diff < 0 and len(C) > 0 and C[-1] > y[-1]:
            cross_yellow = True

        # ==========================================
        # 拐点
        # ==========================================
        inflection = None

        # 向下拐头: 白>黄, 差值缩小 → 预警
        if diff > 0 and gap_shrinking and abs_diff_pct > 1.5:
            inflection = "顶部预警"

        # 向上拐头: 白<黄, 差值缩小 AND 白线开始向上
        if diff < 0 and gap_shrinking and w_slope_1d > 0:
            if y_slope_5d > 0:
                inflection = "拐头向上"
            else:
                inflection = "底部预警"

        # 差值由缩小转为扩大 = 拐头完成
        if self.m >= 3:
            d1 = abs(w[-1] - y[-1])
            d2 = abs(w[-2] - y[-2])
            d3 = abs(w[-3] - y[-3])
            if d1 > d2 and d2 < d3 and abs_diff_pct > 1.5:
                inflection = "拐头确认"

        # ==========================================
        # 状态
        # ==========================================
        # 穿越当天 = 方向已反转, 不看差值缩小逻辑
        if cross == "golden" or (cross_days == 1 and diff > 0):
            state = "多头"
        elif diff > 0:
            if gap_shrinking:
                state = "谨慎"
            else:
                state = "多头"
        elif abs_diff_pct < 0.5 and abs(slope_ratio) < 1.5 / sensitivity:
            state = "纠葛"
        elif diff < 0 and gap_shrinking and w_slope_1d > 0:
            state = "拐头向上"
        elif diff < 0 and y_slope_5d < 0 and not gap_shrinking:
            state = "空头"          # 黄线下行+差值扩大=真弱
        else:
            state = "弱势"          # 黄线下行但差值在缩小

        # ==========================================
        # 评分 (0~10)
        # ==========================================
        score = 5
        if w_slope_1d > 0:
            score += 1
        if w_slope_1d > y_slope_5d:
            score += 1                     # 白线斜率>黄线斜率
        if cross == "golden":
            score += 2
        if cross_days > 0 and cross_days <= 3:
            score += 1
        if not gap_shrinking:
            score += 1                     # 差值扩大
        if abs_diff_pct > 3:
            score += 1                     # 趋势分离充分
        if y_slope_5d > 0.01:
            score += 1
        if w_slope_1d > 0 and y_slope_1d > 0 and slope_ratio > 1.5:
            score += 1                     # 白线显著快于黄线(加速中)
        if cross_yellow:
            score += 1                     # 涨穿黄线
        # 惩罚
        if abs_diff_pct < 0.5 and abs(slope_ratio) < 1.5:
            score -= 2                     # 贴线纠葛
        if diff_pct < -8:
            score -= 1                     # 白深陷黄下, 极度弱势
        if state == "空头":
            score -= 2
        if state == "弱势":
            score -= 1
        if state == "拐头向上":
            score += 1
        if state == "多头":
            score += 1
        score = max(0, min(10, score))

        # ==========================================
        # 信号列表
        # ==========================================
        signals = []
        if w_slope_1d > 0.01:
            signals.append("白线上行")
        elif w_slope_1d < -0.01:
            signals.append("白线下行")
        else:
            signals.append("白线走平")
        if y_slope_5d > 0:
            signals.append("黄线向上")
        else:
            signals.append("黄线向下")
        if w_slope_1d > y_slope_5d and w_slope_1d > 0:
            signals.append("白线加速")
        if cross == "golden":
            signals.append("金叉")
        elif cross == "death":
            signals.append("死叉")
        if cross_yellow:
            signals.append("涨穿黄线")
        if not gap_shrinking:
            signals.append("差值扩大")
        else:
            signals.append("差值缩小")
        if inflection:
            signals.append(inflection)

        return {
            "code": self.code,
            "白": round(w[-1], 3),
            "黄": round(y[-1], 3),
            "差值_pct": round(diff_pct, 2),
            "白_slope_1d": round(w_slope_1d, 4),
            "白_slope_5d": round(w_slope_5d, 4) if self.m >= 6 else None,
            "黄_slope_1d": round(y_slope_1d, 4),
            "黄_slope_5d": round(y_slope_5d, 4) if self.m >= 6 else None,
            "斜率比": round(slope_ratio, 2),
            "差值_trend": "contracting" if gap_shrinking else "expanding",
            "差值_growth": round(diff_growth, 2),
            "cross": cross,
            "cross_days": cross_days,
            "cross_yellow": cross_yellow,
            "inflection": inflection,
            "state": state,
            "score": score,
            "signals": signals,
        }
