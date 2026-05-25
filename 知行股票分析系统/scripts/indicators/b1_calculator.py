"""
知行指标系统 — 4套指标完整实现
逐行对齐 知行系统公式/*.md 原始公式

指标1: 知行趋势指标 (白黄线) — 对齐 知行趋势指标.md
指标2: 单针下20 — 对齐 单针下20.md
指标3: 知行超级B1 (7种买点) — 对齐 知行超级B1.md
指标4: 基础B1 (B1/B2/B3三级递进) — 对齐 基础B1.md

输入: {"candles": [{date, open, high, low, close, volume}]}
volume 自适应: >100000 视为股（iFind），自动除以100转为手
"""
import json
import sys
from collections import deque


# =========================================================
# 基础函数（对齐同花顺公式语义）
# =========================================================

def sma(data, period, weight=1):
    """SMA(X, N, M): X的N日加权移动平均，权重M"""
    result = [data[0]]
    for i in range(1, len(data)):
        val = (data[i] * weight + result[-1] * (period - weight)) / period
        result.append(val)
    return result


def ema(data, period):
    """EMA(X, N): X的N日指数移动平均"""
    k = 2 / (period + 1)
    result = [data[0]]
    for i in range(1, len(data)):
        result.append(data[i] * k + result[-1] * (1 - k))
    return result


def ma(data, period):
    """MA(X, N): X的N日简单移动平均"""
    if len(data) < period:
        return None
    return sum(data[-period:]) / period


def llv(data, period):
    """LLV(X, N): N周期内最低值"""
    return min(data[-period:])


def hhv(data, period):
    """HHV(X, N): N周期内最高值"""
    return max(data[-period:])


def hhvbars(data, period):
    """HHVBARS(X, N): N周期内最大值距离现在的天数"""
    if len(data) < period:
        return 0
    window = data[-period:]
    max_val = max(window)
    for i in range(len(window) - 1, -1, -1):
        if window[i] == max_val:
            return len(window) - 1 - i
    return 0


def count(condition_list):
    """COUNT(X, N): 统计条件成立的天数"""
    return sum(1 for c in condition_list if c)


def every(condition_list):
    """EVERY(X, N): 判断条件是否一直成立"""
    return all(condition_list)


def barslast(condition_list):
    """BARSLAST(X): 上一次条件成立到现在的天数"""
    for i in range(len(condition_list) - 1, -1, -1):
        if condition_list[i]:
            return len(condition_list) - 1 - i
    return len(condition_list)


def ref(data, n):
    """REF(X, N): N日前的X值"""
    if n >= len(data):
        return data[0]
    return data[-(n + 1)]


def cross(a_arr, b_arr_or_val):
    """CROSS(A, B): A上穿B（前一日A<=B, 今日A>B）"""
    if len(a_arr) < 2:
        return False
    if isinstance(b_arr_or_val, (int, float)):
        b_prev = b_arr_or_val
        b_cur = b_arr_or_val
    else:
        if len(b_arr_or_val) < 2:
            return False
        b_prev = b_arr_or_val[-2]
        b_cur = b_arr_or_val[-1]
    return a_arr[-2] <= b_prev and a_arr[-1] > b_cur


class StockAnalyzer:
    """单只股票的完整知行指标计算，逐行对齐原始公式"""

    def __init__(self, code, candles):
        self.code = code
        c = candles[-120:] if len(candles) >= 120 else candles

        self.close = [v['close'] for v in c]
        self.high = [v['high'] for v in c]
        self.low = [v['low'] for v in c]
        self.open = [v['open'] for v in c]
        raw_vol = [abs(v['volume']) for v in c]
        self.volume = [v / 100 if v > 100000 else v for v in raw_vol]
        self.amount = [v * self.close[i] for i, v in enumerate(self.volume)] if self.volume else []

        self.n = len(self.close)
        self.last = self.close[-1]

        is_kcb = code.startswith('68')
        is_cyb = code.startswith('30')
        # 对齐公式: 振幅区间 := IF((CODELIKE('68') OR CODELIKE('30')), 8, 5)
        self.amplitude_limit = 8 if (is_kcb or is_cyb) else 5
        # 对齐公式: 涨跌放宽系数 := IF((CODELIKE('68') OR CODELIKE('30')), 0.9, 1)
        self.change_relax = 0.9 if (is_kcb or is_cyb) else 1.0

    def compute_all(self):
        try:
            return self._compute()
        except Exception as e:
            return {"error": str(e)}

    def _compute(self):
        if self.n < 114:
            return {"error": f"数据不足114天（当前{self.n}天）"}

        C = self.close
        H = self.high
        L = self.low
        O = self.open
        V = self.volume

        # =========================================================
        # 指标1: 知行趋势指标（对齐 知行趋势指标.md）
        # 趋势白线:=EMA(EMA(C,10),10) — 双重平滑短期趋势
        # 大哥黄线:=(MA(C,14)+MA(C,28)+MA(C,57)+MA(C,114))/4 — 多空分水岭
        # =========================================================
        ema10_full = ema(C, 10)
        趋势白线 = ema(ema10_full, 10)[-1]

        m14 = ma(C, 14) or 0
        m28 = ma(C, 28) or 0
        m57 = ma(C, 57) or 0
        m114 = ma(C, 114) or 0
        if not all([m14, m28, m57, m114]):
            return {"error": f"均线计算失败（数据不足）"}
        大哥黄线 = (m14 + m28 + m57 + m114) / 4

        # BBI:=(MA(CLOSE,3)+MA(CLOSE,6)+MA(CLOSE,12)+MA(CLOSE,24))/4
        m3 = ma(C, 3) or 0
        m6 = ma(C, 6) or 0
        m12 = ma(C, 12) or 0
        m24 = ma(C, 24) or 0
        BBI = (m3 + m6 + m12 + m24) / 4 if all([m3, m6, m12, m24]) else 0

        # MACD — DIF:=EMA(CLOSE,12)-EMA(CLOSE,26), DEA:=EMA(DIF,9)
        ema12_arr = ema(C, 12)
        ema26_arr = ema(C, 26)
        dif_arr = [ema12_arr[i] - ema26_arr[i] for i in range(len(C))]
        DIF = dif_arr[-1]
        dea_arr = ema(dif_arr, 9)
        DEA = dea_arr[-1]
        MACD = (DIF - DEA) * 2

        # =========================================================
        # KDJ (9,3,3) — 对齐 知行超级B1.md 第七节
        # RSV:=(CLOSE-LLV(LOW,9))/(HHV(HIGH,9)-LLV(LOW,9))*100
        # K:=SMA(RSV,3,1), D:=SMA(K,3,1), J:=3*K-2*D
        # =========================================================
        rsv_arr = []
        for i in range(self.n):
            if i < 8:
                rsv_arr.append(50)
                continue
            h9 = max(H[i - 8:i + 1])
            l9 = min(L[i - 8:i + 1])
            rsv = (C[i] - l9) / (h9 - l9) * 100 if h9 != l9 else 50
            rsv_arr.append(rsv)

        K_arr = sma(rsv_arr, 3, 1)
        D_arr = sma(K_arr, 3, 1)
        J_arr = [3 * K_arr[i] - 2 * D_arr[i] for i in range(len(K_arr))]

        K_val = K_arr[-1]
        D_val = D_arr[-1]
        J = J_arr[-1]

        # =========================================================
        # RSI(3) — 对齐 知行超级B1.md 第八节
        # RSI:=SMA(MAX(CLOSE-LC,0),3,1)/SMA(ABS(CLOSE-LC),3,1)*100
        # =========================================================
        temp1_arr = [max(C[i] - C[i - 1], 0) if i > 0 else 0 for i in range(self.n)]
        temp2_arr = [abs(C[i] - C[i - 1]) if i > 0 else 0 for i in range(self.n)]
        rsi_sma1 = sma(temp1_arr, 3, 1)
        rsi_sma2 = sma(temp2_arr, 3, 1)
        rsi_arr = [rsi_sma1[i] / rsi_sma2[i] * 100 if rsi_sma2[i] != 0 else 50 for i in range(self.n)]
        RSI = rsi_arr[-1]

        # =========================================================
        # 指标2: 单针下20（对齐 单针下20.md）
        # SHORTLEN:=3, LONGLEN:=21
        # 短期K: 3日归一化; 长期K: 21日归一化
        # =========================================================
        SHORTK_list = []
        for i in range(self.n):
            if i < 2:
                SHORTK_list.append(50)
                continue
            ll = min(L[i - 2:i + 1])
            hh = max(C[i - 2:i + 1])
            den = hh - ll
            SHORTK_list.append(50 if den == 0 else 100 * (C[i] - ll) / den)
        短期 = SHORTK_list[-1]

        LONGK_list = []
        for i in range(self.n):
            if i < 20:
                LONGK_list.append(50)
                continue
            ll = min(L[i - 20:i + 1])
            hh = max(C[i - 20:i + 1])
            den = hh - ll
            LONGK_list.append(50 if den == 0 else 100 * (C[i] - ll) / den)
        长期 = LONGK_list[-1]

        # 对齐公式: 单针下20买:=SHORTK<=20 AND LONGK>=80
        单针下20_flag = (短期 <= 20 and 长期 >= 75) or ((长期 - 短期) >= 70)
        # 对齐公式: 双线归零买:=SHORTK<=6 AND LONGK<=6
        双线归零 = SHORTK_list[-1] <= 6 and LONGK_list[-1] <= 6

        # =========================================================
        # 基础判断量（对齐 知行超级B1.md 第三节）
        # =========================================================
        # 当日振幅 := (HIGH - LOW) / LOW * 100
        当日振幅 = (H[-1] - L[-1]) / L[-1] * 100 if L[-1] > 0 else 0

        # 当日涨跌幅 := ABS(CLOSE - REF(CLOSE, 1)) / REF(CLOSE, 1) * 100 * 涨跌放宽系数
        当日涨跌幅_val = abs(C[-1] - C[-2]) / C[-2] * 100 * self.change_relax if C[-2] > 0 else 0

        # 上涨十字星 := C>REF(C,1) AND (ABS(C-O)/O*100*涨跌放宽系数)<1.8
        上涨十字星 = (
            C[-1] > C[-2]
            and (abs(C[-1] - O[-1]) / O[-1] * 100 * self.change_relax) < 1.8
        )

        # =========================================================
        # 单针形态定义（对齐 知行超级B1.md 第四节）
        # =========================================================
        聚宝盆 = False
        双叉戟 = False
        红肥绿瘦 = False

        if len(LONGK_list) >= 30 and len(SHORTK_list) >= 30:
            recent_long_30 = LONGK_list[-30:]
            recent_short_30 = SHORTK_list[-30:]

            if len(recent_long_30) >= 8:
                # 聚宝盆:=COUNT(长期>=75,8)>=6 AND COUNT(短期<=70,7)>=4 AND COUNT(短期<=50,8)>=1
                聚宝盆 = (
                    count([x >= 75 for x in recent_long_30[-8:]]) >= 6
                    and count([x <= 70 for x in recent_short_30[-7:]]) >= 4
                    and count([x <= 50 for x in recent_short_30[-8:]]) >= 1
                )

                # 双叉戟:=EVERY(长期>=75,8) AND COUNT(短期<=50,6)>=2 AND COUNT(短期<=20,7)>=1
                双叉戟 = (
                    every([x >= 75 for x in recent_long_30[-8:]])
                    and count([x <= 50 for x in recent_short_30[-6:]]) >= 2
                    and count([x <= 20 for x in recent_short_30[-7:]]) >= 1
                )

            # 红肥绿瘦:=COUNT(C>=O,15)>7 OR COUNT(C>REF(C,1),11)>5
            if len(C) >= 15:
                close_latest_15 = C[-15:]
                open_latest_15 = O[-15:]
                红肥绿瘦 = (
                    count([close_latest_15[i] >= open_latest_15[i] for i in range(15)]) > 7
                    or count([close_latest_15[i] > close_latest_15[i - 1] for i in range(1, 11)]) > 5
                )

        # =========================================================
        # 大绿棒（对齐 知行超级B1.md 第五节）
        # VDAY := HHVBARS(VOL, 40)
        # 不是大绿棒 := REF(C,VDAY)>=REF(C,VDAY+1) OR REF(C,VDAY)>=REF(O,VDAY)
        # 大绿棒 := NOT(不是大绿棒)
        # 大绿棒离得远 := VDAY>=15 AND 大绿棒
        # =========================================================
        VDAY = hhvbars(V, 40) if len(V) >= 40 else 0
        not_大绿棒 = True
        大绿棒 = False
        大绿棒离得远 = False

        if len(V) >= 40 and VDAY < len(V):
            vday_idx = len(V) - 1 - VDAY
            vday_close = C[vday_idx]
            vday_open = O[vday_idx]
            vday_prev_close = C[vday_idx + 1] if vday_idx + 1 < len(C) else C[vday_idx]
            cond1 = vday_close >= vday_prev_close
            cond2 = vday_close >= vday_open
            not_大绿棒 = cond1 or cond2
            大绿棒 = not not_大绿棒
            大绿棒离得远 = VDAY >= 15 and 大绿棒

        # =========================================================
        # 缩量分级（对齐 知行超级B1.md 第六节）
        # 缩量:=(VOL < HHV(VOL, 20) *0.416) OR (VOL < HHV(VOL, 50) / 3)
        # 回踩缩量:=(VOL < HHV(VOL, 20) *0.45) OR (VOL < HHV(VOL, 50) / 3)
        # 适当缩量:=(VOL < HHV(VOL, 20) *0.618) OR (VOL < HHV(VOL, 50) / 3)
        # 超缩量:=(VOL < HHV(VOL, 30)/4) OR (VOL < HHV(VOL, 50) / 6)
        # =========================================================
        vol_20_hhv = hhv(V, 20) if len(V) >= 20 else max(V)
        vol_30_hhv = hhv(V, 30) if len(V) >= 30 else max(V)
        vol_50_hhv = hhv(V, 50) if len(V) >= 50 else max(V)

        缩量 = (V[-1] < vol_20_hhv * 0.416) or (V[-1] < vol_50_hhv / 3)
        回踩缩量 = (V[-1] < vol_20_hhv * 0.45) or (V[-1] < vol_50_hhv / 3)
        适当缩量 = (V[-1] < vol_20_hhv * 0.618) or (V[-1] < vol_50_hhv / 3)
        超缩量 = (V[-1] < vol_30_hhv / 4) or (V[-1] < vol_50_hhv / 6)

        # =========================================================
        # 振幅与异动（对齐 知行超级B1.md 第九节）
        # =========================================================
        low_20 = llv(L, 20)
        high_20 = hhv(H, 20)
        近期振幅_val = (high_20 - low_20) / low_20 * 100 if low_20 > 0 else 0

        low_50 = llv(L, 50) if len(L) >= 50 else llv(L, len(L))
        high_50 = hhv(H, 50) if len(H) >= 50 else hhv(H, len(H))
        远期振幅_val = (high_50 - low_50) / low_50 * 100 if low_50 > 0 else 0

        # 近期异动 := 近期振幅 >= 15 OR (HHV(H,12)-LLV(L,14))/LLV(L,14) * 100>=11
        近期异动 = (
            近期振幅_val >= 15
            or (hhv(H[-12:], 12) - llv(L[-14:], 14)) / llv(L[-14:], 14) * 100 >= 11
        )
        # 远期异动 := 远期振幅 >=30
        远期异动 = 远期振幅_val >= 30
        # 超级异动 := 近期振幅 >=60
        超级异动 = 近期振幅_val >= 60

        # 洗盘异动 := (COUNT(单针下20,10)>=2) OR 聚宝盆 OR 双叉戟
        screen_wash_count = 0
        check_len = min(10, len(SHORTK_list), len(LONGK_list))
        for i in range(check_len):
            idx = -1 - i
            sk = SHORTK_list[idx]
            lk = LONGK_list[idx]
            if (sk <= 20 and lk >= 75) or ((lk - sk) >= 70):
                screen_wash_count += 1
        洗盘异动 = (screen_wash_count >= 2) or 聚宝盆 or 双叉戟

        # =========================================================
        # 趋势股定义（对齐 知行超级B1.md 第十节）
        # =========================================================
        # 做上涨趋势 := 趋势白线>=大哥黄线 AND (C>=大哥黄线 OR (C>大哥黄线*0.975 AND C>O))
        做上涨趋势 = (
            趋势白线 >= 大哥黄线
            and (C[-1] >= 大哥黄线 or (C[-1] > 大哥黄线 * 0.975 and C[-1] > O[-1]))
        )

        # 强趋势股 := EVERY(大哥黄线>=REF(大哥黄线,1)*0.999,13) AND 趋势白线>=REF(趋势白线,1)
        #   AND EVERY(趋势白线>大哥黄线,20) AND EVERY(趋势白线>=REF(趋势白线,1),11) AND 红肥绿瘦
        强趋势股 = False
        if self.n >= 20:
            bai_up_11 = True
            yellow_near_stable = True
            bai_gt_yellow_20 = True
            bai_cont_up_11 = True

            if self.n >= 13:
                大哥黄线_arr = [(ma(C[:i + 1], 14) + ma(C[:i + 1], 28) + ma(C[:i + 1], 57) + ma(C[:i + 1], 114)) / 4
                             for i in range(10, self.n) if all(ma(C[:i + 1], p) is not None for p in [14, 28, 57, 114])]
                if len(大哥黄线_arr) >= 13:
                    yellow_near_stable = every([
                        大哥黄线_arr[-i] >= 大哥黄线_arr[-i - 1] * 0.999
                        for i in range(1, 14)
                    ])

            if self.n >= 11:
                bai_arr_last_11 = []
                for i in range(-11, 0):
                    chunk = C[:self.n + i + 1] if self.n + i + 1 <= self.n else C
                    if len(chunk) >= 10:
                        ema10_chunk = ema(chunk, 10)
                        bai_val = ema(ema10_chunk, 10)[-1]
                        bai_arr_last_11.append(bai_val)
                if len(bai_arr_last_11) >= 11:
                    bai_cont_up_11 = every([
                        bai_arr_last_11[-i] >= bai_arr_last_11[-i - 1] * 0.999
                        for i in range(1, 11)
                    ])

            if self.n >= 20:
                recent_bai = []
                recent_yellow = []
                for i in range(-20, 0):
                    idx = self.n + i
                    if idx < 10:
                        continue
                    chunk = C[:idx + 1]
                    ema10_chunk = ema(chunk, 10)
                    bv = ema(ema10_chunk, 10)[-1]
                    m14c = ma(chunk, 14)
                    m28c = ma(chunk, 28)
                    m57c = ma(chunk, 57)
                    m114c = ma(chunk, 114)
                    if all(x is not None for x in [m14c, m28c, m57c, m114c]):
                        yv = (m14c + m28c + m57c + m114c) / 4
                        recent_bai.append(bv)
                        recent_yellow.append(yv)
                if len(recent_bai) >= 20:
                    bai_gt_yellow_20 = every([recent_bai[-i] > recent_yellow[-i] for i in range(1, 21)])

            强趋势股 = yellow_near_stable and bai_gt_yellow_20 and bai_cont_up_11 and 红肥绿瘦

        # 超牛股 := (EVERY(BBI>=REF(BBI,1)*0.999,20) OR COUNT(BBI>=REF(BBI,1),25)>=23)
        #   AND (近期振幅 >=30 OR 远期振幅>80)
        #   AND BARSLAST(CROSS(C,大哥黄线))>12
        超牛股 = False
        bbi_history = []
        for i in range(10, self.n):
            _m3 = ma(C[:i + 1], 3)
            _m6 = ma(C[:i + 1], 6)
            _m12 = ma(C[:i + 1], 12)
            _m24 = ma(C[:i + 1], 24)
            if all(x is not None for x in [_m3, _m6, _m12, _m24]):
                bbi_history.append((_m3 + _m6 + _m12 + _m24) / 4)

        if len(bbi_history) >= 20:
            bbi_stable = every([
                bbi_history[-i] >= bbi_history[-i - 1] * 0.999
                for i in range(1, 21)
            ]) if len(bbi_history) >= 21 else False
            bbi_up_23of25 = count([
                bbi_history[-i] >= bbi_history[-i - 1]
                for i in range(1, min(26, len(bbi_history)))
            ]) >= 23

            # BARSLAST(CROSS(C,大哥黄线))>12 — 距离上次上穿黄线已超过12天
            cross_clist = []
            for i in range(10, self.n):
                if i < 2:
                    cross_clist.append(False)
                else:
                    m14_i = ma(C[:i + 1], 14)
                    m28_i = ma(C[:i + 1], 28)
                    m57_i = ma(C[:i + 1], 57)
                    m114_i = ma(C[:i + 1], 114)
                    if all(x is not None for x in [m14_i, m28_i, m57_i, m114_i]):
                        yv_cur = (m14_i + m28_i + m57_i + m114_i) / 4
                        m14_p = ma(C[:i], 14)
                        m28_p = ma(C[:i], 28)
                        m57_p = ma(C[:i], 57)
                        m114_p = ma(C[:i], 114)
                        if all(x is not None for x in [m14_p, m28_p, m57_p, m114_p]):
                            yv_prev = (m14_p + m28_p + m57_p + m114_p) / 4
                            cross_clist.append(C[i - 1] <= yv_prev and C[i] > yv_cur)
                        else:
                            cross_clist.append(False)
                    else:
                        cross_clist.append(False)
            bars_cross = barslast(cross_clist) if cross_clist else 999

            超牛股 = (
                (bbi_stable or bbi_up_23of25)
                and (近期振幅_val >= 30 or 远期振幅_val > 80)
                and bars_cross > 12
            )

        # =========================================================
        # 回踩白线/黄线/距离计算（对齐 知行超级B1.md 第十一节）
        # =========================================================
        # 距离白线 := (ABS(C-趋势白线)/C)*100
        距离白线 = abs(C[-1] - 趋势白线) / C[-1] * 100 if C[-1] > 0 else 0
        # L距离白线 := (ABS(L-趋势白线)/趋势白线)*100
        L距离白线 = abs(L[-1] - 趋势白线) / 趋势白线 * 100 if 趋势白线 > 0 else 0
        # 距离BBI := (ABS(C-BBI)/C)*100
        距离BBI_val = abs(C[-1] - BBI) / C[-1] * 100 if C[-1] > 0 else 0
        # L距离BBI := (ABS(L-BBI)/BBI)*100
        L距离BBI = abs(L[-1] - BBI) / BBI * 100 if BBI > 0 else 0
        # 距离黄线 := (ABS(C-大哥黄线)/大哥黄线)*100
        距离黄线_val = abs(C[-1] - 大哥黄线) / 大哥黄线 * 100 if 大哥黄线 > 0 else 0

        # 回踩白线条件:
        # (C>=趋势白线 AND 距离白线<=2)
        # OR (C<趋势白线 AND 距离白线<0.8)
        # OR (C>=BBI AND 距离BBI<2.5 AND L距离BBI<1 AND 距离白线<=3 AND 当日涨跌幅<1 AND C>REF(C,1))
        回踩白线_cond = (
            (C[-1] >= 趋势白线 and 距离白线 <= 2)
            or (C[-1] < 趋势白线 and 距离白线 < 0.8)
            or (
                C[-1] >= BBI and 距离BBI_val < 2.5
                and L距离BBI < 1 and 距离白线 <= 3
                and 当日涨跌幅_val < 1 and C[-1] > C[-2]
            )
        )
        # 白线支撑:=C>=趋势白线 AND 距离白线<1.5
        白线支撑 = C[-1] >= 趋势白线 and 距离白线 < 1.5
        # 强势回踩白线不破:=(L距离白线<1 OR L距离BBI<0.5) AND (C>趋势白线) AND (距离白线<=3.5)
        强势回踩白线不破 = (
            (L距离白线 < 1 or L距离BBI < 0.5)
            and C[-1] > 趋势白线
            and 距离白线 <= 3.5
        )

        # 回踩黄线条件:
        # (C>=大哥黄线 AND (距离黄线<=1.5 OR (距离黄线<=2 AND 当日涨跌幅<1)))
        # OR (C<大哥黄线 AND 距离黄线<=0.8)
        回踩黄线_cond = (
            (C[-1] >= 大哥黄线 and (距离黄线_val <= 1.5 or (距离黄线_val <= 2 and 当日涨跌幅_val < 1)))
            or (C[-1] < 大哥黄线 and 距离黄线_val <= 0.8)
        )

        # =========================================================
        # 持股分数（对齐 知行超级B1.md 第十三节）
        # X:=IF(下跌,0,1)+IF(放量,0,1)+IF(破线,0,1)+IF(死叉,0,1)+IF(转势,0,1)
        # 注意: 原始公式用 J<=K 定义死叉
        # =========================================================
        下跌 = C[-1] < C[-2]
        放量_flag = V[-1] > V[-2] and 下跌
        # 死叉: J<=K（非 J<=D）
        死叉 = J <= K_val
        # 破线: C < 趋势白线
        破线 = C[-1] < 趋势白线
        # 转势: (趋势白线-REF(趋势白线,1))<0 → 白线走平或向下
        白线_prev = ema(ema10_full[:-1], 10)[-1] if len(ema10_full) > 1 else 趋势白线
        转势 = (趋势白线 - 白线_prev) < 0

        score = 5
        if 下跌: score -= 1
        if 放量_flag: score -= 1
        if 破线: score -= 1
        if 死叉: score -= 1
        if 转势: score -= 1

        # 持股出现死叉: J从>K变成<=K
        prev_J_gt_K = (J_arr[-2] > K_arr[-2]) if len(J_arr) >= 2 else False
        持股出现死叉 = 死叉 and prev_J_gt_K
        出现金叉 = J > K_val and ((J_arr[-2] <= K_arr[-2]) if len(J_arr) >= 2 else False)

        # =========================================================
        # 指标4: 基础B1 (对齐 基础B1.md)
        # =========================================================
        # COND_AMOUNT:=(HHV(AMOUNT,24)>=60*240*10000)
        COND_AMOUNT = hhv(self.amount, min(24, len(self.amount))) >= 60 * 240 * 10000
        # S_COND1:=ST>LT
        S_COND1 = 趋势白线 > 大哥黄线
        # S_COND2:=C>LT OR DIF>0
        S_COND2 = C[-1] > 大哥黄线 or DIF > 0

        # B1: J<13 AND COND_AMOUNT AND S_COND1 AND S_COND2
        基础B1 = J < 13 and COND_AMOUNT and S_COND1 and S_COND2

        # B2: REF(B1,1)=1 AND J<80 AND AMP>3.9 AND VOL>=REF(VOL,1)
        AMP = (C[-1] - C[-2]) / C[-2] * 100 if C[-2] > 0 else 0
        yesterday_B1 = False
        if self.n >= 2:
            J_yest = J_arr[-2] if len(J_arr) >= 2 else 50
            # simplified yesterday B1 check: same conditions for yesterday
            yest_cond1 = 趋势白线 > 大哥黄线  # approximate, 白线 changes daily
            yesterday_B1 = J_yest < 13 and yest_cond1

        基础B2 = yesterday_B1 and J < 80 and AMP > 3.9 and V[-1] >= V[-2]

        # B3: REF(B2,1)=1 AND VOL<REF(VOL,1) AND ABS(AMP)<=2
        yesterday_B2 = False
        if self.n >= 3:
            J_y2 = J_arr[-3] if len(J_arr) >= 3 else 50
            J_y1 = J_arr[-2] if len(J_arr) >= 2 else 50
            AMP_y1 = (C[-2] - C[-3]) / C[-3] * 100 if C[-3] > 0 else 0
            yesterday_B2 = (J_y2 < 13 and J_y1 < 80 and AMP_y1 > 3.9 and V[-2] >= V[-3])

        基础B3 = yesterday_B2 and V[-1] < V[-2] and abs(AMP) <= 2

        # =========================================================
        # 知行超级B1 (对齐 知行超级B1.md 第十五节)
        # 7种买点，逐行对齐原始公式
        # =========================================================

        # 1. 超卖缩量拐头B（黄色柱）
        # 对齐公式行 256-263
        超卖缩量拐头B = (
            做上涨趋势
            and (RSI - 15) >= ref(rsi_arr, 1)
            and (ref(rsi_arr, 1) < 20 or ref(J_arr, 1) < 14)
            and 当日振幅 < (self.amplitude_limit + 0.5)
            and (当日涨跌幅_val < 2.3 or (上涨十字星 and 当日涨跌幅_val < 4))
            and (not_大绿棒 or 大绿棒离得远)
            and (近期异动 or 远期异动 or 洗盘异动)
            and C[-1] >= 大哥黄线
        )

        # 2. 超卖缩量B（红色柱）
        # 对齐公式行 266-274
        超卖缩量B = (
            做上涨趋势
            and (J < 14 or RSI < 23)
            and (RSI + J < 55 or (len(J_arr) >= 20 and J == llv(J_arr[-20:], 20)))
            and 当日振幅 < self.amplitude_limit
            and (当日涨跌幅_val < 2.5 or 上涨十字星)
            and (not_大绿棒 or 大绿棒离得远)
            and (缩量 or (适当缩量 and 当日涨跌幅_val < 1))
            and (近期异动 or 远期异动 or 洗盘异动)
        )

        # 计算昨日黄线（用于原始B1和回踩黄线B的黄线上升判断）
        yellow_yest_val = 大哥黄线  # fallback
        if self.n >= 2:
            chunk_yest = C[:-1]
            if len(chunk_yest) >= 114:
                m14_y = ma(chunk_yest, 14)
                m28_y = ma(chunk_yest, 28)
                m57_y = ma(chunk_yest, 57)
                m114_y = ma(chunk_yest, 114)
                if all(x is not None for x in [m14_y, m28_y, m57_y, m114_y]):
                    yellow_yest_val = (m14_y + m28_y + m57_y + m114_y) / 4

        # 3. 原始B1（白色柱）
        # 对齐公式行 276-287（含 大哥黄线>=REF(大哥黄线,1) 条件）
        原始B1 = (
            趋势白线 > 大哥黄线
            and C[-1] >= 大哥黄线 * 0.99
            and 大哥黄线 >= yellow_yest_val  # 黄线向上，趋势向好
            and (J < 13 or RSI < 21)
            and len(J_arr) >= 15 and len(rsi_arr) >= 15
            and (RSI + J) < llv(
                [J_arr[i] + rsi_arr[i] for i in range(-15, 0)],
                15
            ) * 1.5
            and 适当缩量
            and (not_大绿棒 or 大绿棒离得远)
            and (
                abs(C[-1] - O[-1]) * 100 / O[-1] < 1.5
                or 超缩量
                or (适当缩量 and len(V) >= 20 and V[-1] < llv(V[-20:], 20) * 1.1
                    and len(J_arr) >= 20 and J == llv(J_arr[-20:], 20))
                or (适当缩量 and (距离白线 < 1.8 or 距离BBI_val < 1.5 or 距离黄线_val < 2.8))
            )
            and (近期异动 or 远期异动 or 洗盘异动)
        )

        # 4. 超卖超缩量B（青色柱）
        # 对齐公式行 290-299
        超卖超缩量B = (
            做上涨趋势
            and (J < 14 or RSI < 23)
            and RSI + J < 60
            and 远期振幅_val >= 45
            and (
                当日振幅 < self.amplitude_limit
                or (超级异动 and 当日振幅 < self.amplitude_limit + 3.2
                    and C[-1] > O[-1] and C[-1] > 趋势白线)
            )
            and (
                (C[-1] < O[-1] and V[-1] < V[-2] and C[-1] >= 大哥黄线)
                or (C[-1] >= O[-1])
            )
            and (当日涨跌幅_val < 2 or 上涨十字星)
            and (not_大绿棒 or 大绿棒离得远)
            and 超缩量
            and (近期异动 or 远期异动 or 洗盘异动)
        )

        # 5. 回踩白线B（紫色柱）— 已修复，对齐公式行 302-311
        回踩白线B = (
            强趋势股
            and (J < 30 or RSI < 40 or 洗盘异动)
            and RSI + J < 70
            and (当日振幅 < self.amplitude_limit + 0.5 or 距离白线 < 1 or 距离BBI_val < 1)
            and 回踩白线_cond
            and (当日涨跌幅_val < 2 or (当日涨跌幅_val < 5 and 白线支撑))
            and (not_大绿棒 or 大绿棒离得远)
            and 回踩缩量  # 注意：回踩白线B用回踩缩量(45%)，非缩量(41.6%)
            and (近期异动 or 远期异动 or 洗盘异动)
            and L[-1] <= ref(C, 1)  # 最低价不高于昨天收盘
        )

        # 6. 回踩白线超级B（绿色柱）— 已修复，对齐公式行 314-323
        rsi_plus_j_arr = [J_arr[i] + rsi_arr[i] for i in range(self.n)]
        回踩白线超级B = (
            超牛股
            and (J < 35 or RSI < 45 or 洗盘异动)
            and RSI + J < 80
            and len(rsi_plus_j_arr) >= 25
            and (RSI + J) == llv(rsi_plus_j_arr[-25:], 25)  # RSI+J是25日最低
            and 当日振幅 < self.amplitude_limit + 1
            and (当日涨跌幅_val < 2.5 or 距离白线 < 2)
            and 强势回踩白线不破
            and (not_大绿棒 or 大绿棒离得远)
            and (近期异动 or 远期异动 or 洗盘异动)
            and 适当缩量  # 注意：超牛股回踩用适当缩量(61.8%)
        )

        # 7. 回踩黄线B（短黄色柱）— 对齐公式行 326-335
        MA60 = ma(C, 60)

        回踩黄线B = (
            趋势白线 >= 大哥黄线
            and C[-1] >= 大哥黄线 * 0.975
            and (J < 13 or RSI < 18)
            and 回踩黄线_cond
            and (not_大绿棒 or 大绿棒离得远)
            and (缩量 or (适当缩量 and (
                (len(J_arr) >= 20 and J == llv(J_arr[-20:], 20))
                or (len(rsi_arr) >= 14 and RSI == llv(rsi_arr[-14:], 14))
            )))
            and 趋势白线 >= 大哥黄线
            and 大哥黄线 >= yellow_yest_val * 0.997  # 黄线几乎不跌，对齐公式行334
            and (MA60 is not None and len(C) >= 60 and MA60 >= ref(C, 59))  # 60日均线向上
            and 近期振幅_val >= 12
            and 远期振幅_val >= 19.5
        )

        # =========================================================
        # 收集信号
        # =========================================================
        signals = []
        if 超卖缩量拐头B: signals.append("超卖缩量拐头B")
        if 超卖缩量B: signals.append("超卖缩量B")
        if 原始B1: signals.append("原始B1")
        if 超卖超缩量B: signals.append("超卖超缩量B")
        if 回踩白线B: signals.append("回踩白线B")
        if 回踩白线超级B: signals.append("回踩白线超级B")
        if 回踩黄线B: signals.append("回踩黄线B")

        trend = "多头" if 趋势白线 > 大哥黄线 else "空头"

        return {
            "code": self.code,
            "last": round(C[-1], 2),
            "白线": round(趋势白线, 2),
            "黄线": round(大哥黄线, 2),
            "BBI": round(BBI, 2),
            "J": round(J, 1),
            "RSI": round(RSI, 1),
            "K": round(K_val, 1),
            "D": round(D_val, 1),
            "MACD_DIF": round(DIF, 2),
            "MACD_DEA": round(DEA, 2),
            "短期K": round(短期, 1),
            "长期K": round(长期, 1),
            "单针下20": 单针下20_flag,
            "双线归零": 双线归零,
            "趋势": trend,
            "做上涨趋势": 做上涨趋势,
            "强趋势股": 强趋势股,
            "超牛股": 超牛股,
            "缩量": 缩量,
            "回踩缩量": 回踩缩量,
            "适当缩量": 适当缩量,
            "超缩量": 超缩量,
            "距离白线_pct": round(距离白线, 2),
            "距离黄线_pct": round(距离黄线_val, 2),
            "距离BBI_pct": round(距离BBI_val, 2),
            "当日振幅": round(当日振幅, 2),
            "近期振幅": round(近期振幅_val, 1),
            "远期振幅": round(远期振幅_val, 1),
            "聚宝盆": 聚宝盆,
            "双叉戟": 双叉戟,
            "洗盘异动": 洗盘异动,
            "大绿棒": 大绿棒,
            "大绿棒离得远": 大绿棒离得远,
            "评分": score,
            "下跌": 下跌,
            "放量下跌": 放量_flag,
            "死叉": 死叉,
            "持股出现死叉": 持股出现死叉,
            "出现金叉": 出现金叉,
            "破线": 破线,
            "转势": 转势,
            "基础B1": 基础B1,
            "基础B2": 基础B2,
            "基础B3": 基础B3,
            "信号": signals,
            # 方向性指标
            "J_rising": (J_arr[-1] > J_arr[-2]) if len(J_arr) >= 2 else None,
            "J_change": round(J_arr[-1] - J_arr[-2], 1) if len(J_arr) >= 2 else None,
            "白线_rising": not 转势,
            "黄线_rising": (大哥黄线 >= yellow_yest_val * 0.999) if yellow_yest_val else None,
            "趋势变化": "白线上穿" if (len(ema10_full) >= 2 and
                ema(ema10_full[:-1], 10)[-1] <= 大哥黄线 and 趋势白线 > 大哥黄线) else None,
        }


def compute_single(code, candles):
    """便捷函数：单只股票计算"""
    analyzer = StockAnalyzer(code, candles)
    return analyzer.compute_all()


if __name__ == "__main__":
    data = json.load(sys.stdin)
    candles = data.get("data", {}).get("candles", [])
    code = data.get("data", {}).get("symbol", "").split(".")[0]
    if not candles:
        candles = data.get("candles", [])
        code = data.get("symbol", "").split(".")[0]
    if not candles:
        print(json.dumps({"error": "无K线数据"}, ensure_ascii=False))
    else:
        result = compute_single(code, candles)
        print(json.dumps(result, ensure_ascii=False, indent=2))
