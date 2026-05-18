"""
板块名册 — iFind 概念板块列表 + 用户查询模糊匹配
数据来源: iFind leaderboard_screen 返回的 所属概念 字段（389+概念）
"""
import json
import os
from typing import List, Set

# 核心概念板块列表（从 iFind leaderboard 提取 + 常见补充）
# 格式: 用户可能搜索的别名 → iFind 标准概念名
_CONCEPT_ALIASES = {
    # 锂电池相关
    "锂电池": "锂电池概念", "锂电": "锂电池概念", "电池": "锂电池概念",
    "锂矿": "盐湖提锂", "锂": "盐湖提锂",
    "固态电池": "固态电池", "钠电池": "钠离子电池", "钠离子": "钠离子电池",
    "动力电池": "动力电池回收", "燃料电池": "燃料电池",
    # 光伏/新能源
    "光伏": "光伏概念", "太阳能": "光伏概念",
    "新能源": "新能源汽车", "新能源车": "新能源汽车",
    "储能": "储能概念",
    # 半导体/芯片
    "芯片": "芯片概念", "半导体": "芯片概念",
    "存储": "存储芯片", "汽车芯片": "汽车芯片",
    # AI/机器人
    "AI": "AI应用", "人工智能": "AI应用",
    "机器人": "机器人概念", "人形机器人": "人形机器人",
    "算力": "算力概念",
    # 能源/金属
    "能源金属": "能源金属",
    "稀土": "稀土永磁", "永磁": "稀土永磁",
    # 其他热门
    "低空经济": "低空经济", "飞行汽车": "低空经济",
    "CPO": "CPO概念", "光模块": "CPO概念",
    "PCB": "PCB概念",
    "消费电子": "消费电子概念",
    "医药": "医药概念", "创新药": "创新药概念",
    "军工": "军工概念", "航天": "航天概念",
    "电力": "电力概念", "电网": "智能电网",
    "数据要素": "数据要素", "数据": "数据要素",
    "华为": "华为概念", "鸿蒙": "鸿蒙概念",
    "汽车": "新能源汽车", "智能驾驶": "智能驾驶",
    "量子": "量子科技", "6G": "6G概念",
}


def fuzzy_match_sectors(user_query: str) -> List[str]:
    """
    用户查询 → 匹配的 iFind 标准概念名列表

    支持:
    - 空格分隔的多关键词: "锂矿 锂电池" → ["盐湖提锂", "锂电池概念"]
    - 单个关键词: "固态电池" → ["固态电池"]
    - 别名映射: "锂电" → "锂电池概念"
    """
    matched = set()

    # 1. 精确匹配（用户输入与映射表 key 完全一致）
    q_lower = user_query.strip()
    if q_lower in _CONCEPT_ALIASES:
        matched.add(_CONCEPT_ALIASES[q_lower])

    # 2. 空格/逗号/顿号 分词匹配
    import re
    tokens = re.split(r'[\s,，、]+', user_query.strip())
    for token in tokens:
        token = token.strip()
        if not token:
            continue
        # 精确 key 匹配
        if token in _CONCEPT_ALIASES:
            matched.add(_CONCEPT_ALIASES[token])
        # 子串匹配（用户输入包含 key, 或 key 包含用户输入）
        for alias, concept in _CONCEPT_ALIASES.items():
            if token in alias or alias in token:
                matched.add(concept)

    # 3. 直接尝试用户输入作为概念名（iFind 可能支持）
    if not matched:
        matched.add(user_query.strip())

    # 去重并保持顺序
    return sorted(matched)


def get_concept_alias_map() -> dict:
    """返回完整别名映射（供 CLI --list-sectors 使用）"""
    return dict(_CONCEPT_ALIASES)


def list_known_concepts() -> List[str]:
    """列出所有已知的 iFind 概念名"""
    return sorted(set(_CONCEPT_ALIASES.values()))
