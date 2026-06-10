"""
股票黑名单配置 — 排除不可交易的板块/类型

SKILL 初始化时提示用户配置，也可通过环境变量覆盖:
  ZX_BAN_BOARDS=688,920,8    # 排除科创板(688)/北交所(920,8开头)
  ZX_BAN_ST=True              # 排除ST
  ZX_BAN_CODES=000001,000002  # 排除指定代码
"""
import os
import json
from dataclasses import dataclass, field
from typing import List, Set


@dataclass
class Blacklist:
    """股票黑名单"""
    ban_boards: Set[str] = field(default_factory=lambda: {"688", "920", "8"})
    ban_st: bool = True
    ban_codes: Set[str] = field(default_factory=set)

    # 用户可自行配置: 是否开启（默认开启）
    # 说明: 北交所(920,8开头) / 科创板(688) / ST 默认排除
    # 原因: 流动性差 / 涨跌幅限制不同 / 风险高

    def is_banned(self, code: str, name: str = "") -> bool:
        """检查股票是否被排除"""
        # 代码前缀匹配
        for prefix in self.ban_boards:
            if code.startswith(prefix):
                return True
        # 精确代码排除
        if code in self.ban_codes:
            return True
        # ST/PT/退市 排除
        if self.ban_st and name:
            upper = name.upper()
            if 'ST' in upper or 'PT' in upper or '退' in name:
                return True
        return False

    def filter_stocks(self, stocks: list, code_attr: str = "code", name_attr: str = "name") -> list:
        """过滤股票列表，返回过滤后的列表和被排除的列表"""
        kept = []
        banned = []
        for s in stocks:
            code = getattr(s, code_attr, s.get(code_attr, "")) if isinstance(s, dict) else getattr(s, code_attr, "")
            name = getattr(s, name_attr, s.get(name_attr, "")) if isinstance(s, dict) else getattr(s, name_attr, "")
            if self.is_banned(str(code), str(name)):
                banned.append(s)
            else:
                kept.append(s)
        return kept, banned

    def summary(self) -> str:
        lines = ["当前排除规则:"]
        if self.ban_boards:
            lines.append(f"  板块: {', '.join(sorted(self.ban_boards))}开头 (如 688=科创板, 920/8=北交所)")
        if self.ban_st:
            lines.append(f"  ST/*ST: 已排除")
        if self.ban_codes:
            lines.append(f"  指定代码: {', '.join(sorted(self.ban_codes))}")
        return '\n'.join(lines)


def load_blacklist() -> Blacklist:
    """从环境变量加载黑名单配置"""
    bl = Blacklist()

    # 环境变量覆盖
    boards_env = os.environ.get("ZX_BAN_BOARDS", "")
    if boards_env:
        bl.ban_boards = set(b.strip() for b in boards_env.split(",") if b.strip())

    if os.environ.get("ZX_BAN_ST", "").lower() in ("0", "false", "no"):
        bl.ban_st = False

    codes_env = os.environ.get("ZX_BAN_CODES", "")
    if codes_env:
        bl.ban_codes = set(c.strip() for c in codes_env.split(",") if c.strip())

    return bl


# 全局默认实例
blacklist = load_blacklist()
