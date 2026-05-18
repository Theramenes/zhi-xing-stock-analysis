"""
缓存管理 — 按日期分片 + 历史对比
目录结构: data/scan_cache/{YYYY-MM-DD}/{code}.json
latest/ 目录存最新缓存快照，方便快速加载
"""
import json
import os
from datetime import date
from typing import Optional


class CacheManager:
    """扫描缓存管理器"""

    def __init__(self, base_dir: str = None):
        if base_dir is None:
            base_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "data", "scan_cache"
            )
        self.base_dir = base_dir
        self.today = date.today().isoformat()

    def _date_dir(self, d: str = None) -> str:
        d = d or self.today
        p = os.path.join(self.base_dir, d)
        os.makedirs(p, exist_ok=True)
        return p

    def save(self, code: str, candles: list, indicators: dict = None):
        """保存K线和指标到今日缓存"""
        fpath = os.path.join(self._date_dir(), f"{code}.json")
        data = {"candles": candles, "date": self.today}
        if indicators:
            data["indicators"] = indicators
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def load(self, code: str, d: str = None) -> Optional[dict]:
        """加载指定日期的缓存"""
        fpath = os.path.join(self._date_dir(d), f"{code}.json")
        if not os.path.exists(fpath):
            return None
        with open(fpath, "r", encoding="utf-8") as f:
            return json.load(f)

    def load_latest(self, code: str) -> Optional[dict]:
        """加载最新可用的缓存（遍历日期目录找最近的）"""
        if not os.path.exists(self.base_dir):
            return None
        dirs = sorted(
            [d for d in os.listdir(self.base_dir)
             if os.path.isdir(os.path.join(self.base_dir, d))],
            reverse=True
        )
        for d in dirs:
            result = self.load(code, d)
            if result:
                return result
        return None

    def load_candles(self, code: str) -> Optional[list]:
        """便捷方法：只取K线数据"""
        cached = self.load_latest(code)
        if cached:
            return cached.get("candles")
        return None

    def load_indicators(self, code: str) -> Optional[dict]:
        """便捷方法：只取指标数据"""
        cached = self.load_latest(code)
        if cached:
            return cached.get("indicators")
        return None

    def get_cached_codes(self, d: str = None) -> set:
        """获取某日已缓存的所有代码"""
        dir_path = self._date_dir(d)
        if not os.path.exists(dir_path):
            return set()
        return {f.replace(".json", "") for f in os.listdir(dir_path) if f.endswith(".json")}

    def compare_with_prev(self, code: str) -> dict:
        """对比今日指标与上一次缓存的差异，返回变化摘要"""
        today_data = self.load(code)
        if not today_data or not today_data.get("indicators"):
            return {"code": code, "changed": False, "note": "今日无数据"}

        dirs = sorted(
            [d for d in os.listdir(self.base_dir)
             if os.path.isdir(os.path.join(self.base_dir, d)) and d != self.today],
            reverse=True
        )
        prev_indicators = None
        prev_date = None
        for d in dirs:
            prev = self.load(code, d)
            if prev and prev.get("indicators"):
                prev_indicators = prev["indicators"]
                prev_date = d
                break

        if not prev_indicators:
            return {"code": code, "changed": True, "note": f"首次缓存"}

        today_ind = today_data["indicators"]
        changes = []

        # 关键指标变化检测
        if today_ind.get("J", 0) != prev_indicators.get("J", 0):
            changes.append(f"J: {prev_indicators['J']:.0f}→{today_ind['J']:.0f}")
        if today_ind.get("评分", 0) != prev_indicators.get("评分", 0):
            changes.append(f"评分: {prev_indicators['评分']}→{today_ind['评分']}")
        if today_ind.get("趋势") != prev_indicators.get("趋势"):
            changes.append(f"趋势: {prev_indicators['趋势']}→{today_ind['趋势']}")

        today_sigs = set(today_ind.get("信号", []))
        prev_sigs = set(prev_indicators.get("信号", []))
        new_sigs = today_sigs - prev_sigs
        lost_sigs = prev_sigs - today_sigs
        if new_sigs:
            changes.append(f"新增信号: {', '.join(new_sigs)}")
        if lost_sigs:
            changes.append(f"消失信号: {', '.join(lost_sigs)}")

        return {
            "code": code,
            "changed": len(changes) > 0,
            "prev_date": prev_date,
            "changes": changes,
        }
