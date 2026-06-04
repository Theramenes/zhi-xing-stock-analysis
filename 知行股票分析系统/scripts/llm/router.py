"""
LLM 语义路由 — 把模糊的用户输入解析为具体的行业/板块列表

用法: resolve_query_to_sectors("低位行业有哪些", market_context)
"""
import json
from typing import List, Dict, Optional


def _build_sector_list() -> list:
    """从 sector_index 获取可用行业列表"""
    try:
        from storage.db import get_db
        db = get_db()
        rows = db.conn.execute(
            "SELECT sector_name, COUNT(*) as cnt FROM sector_index "
            "GROUP BY sector_name HAVING cnt>=10 ORDER BY cnt DESC"
        ).fetchall()
        return [f"{r[0]}({r[1]}只)" for r in rows]
    except Exception:
        return []


def _build_market_context() -> str:
    """拼接市场上下文给LLM"""
    lines = []
    try:
        from storage.db import get_db
        db = get_db()
        # 指数
        for code, name in [("000001","上证"),("399006","创业板"),("000688","科创50")]:
            row = db.conn.execute(
                "SELECT date,close FROM index_daily WHERE code=? ORDER BY date DESC LIMIT 4", (code,)
            ).fetchall()
            if len(row) >= 2:
                chg = (row[0][1] - row[-1][1]) / row[-1][1] * 100
                lines.append(f"{name}: 最新{row[0][1]:.1f} 近3日{chg:+.1f}%")
        # B1 密度
        scan_id = db.conn.execute(
            "SELECT scan_id FROM b1_scan WHERE b1_count>0 "
            "AND (SELECT COUNT(*) FROM b1_candidate WHERE scan_id=b1_scan.scan_id AND category='B1')>0 "
            "ORDER BY scan_id DESC LIMIT 1"
        ).fetchone()
        if scan_id and scan_id[0]:
            rows = db.conn.execute(
                "SELECT si.sector_name, COUNT(*) as cnt FROM b1_candidate bc "
                "LEFT JOIN sector_index si ON bc.code=si.code "
                f"WHERE bc.scan_id={scan_id[0]} AND bc.category='B1' "
                "GROUP BY si.sector_name ORDER BY cnt DESC LIMIT 10"
            ).fetchall()
            if rows:
                lines.append("B1密度前10: " + ", ".join(f"{r[0] or '?'}:{r[1]}只" for r in rows))
    except Exception:
        pass
    return "\n".join(lines)


def resolve_query_to_sectors(query: str) -> Optional[dict]:
    """把自然语言解析为行业列表。

    Returns: {"sectors": [...], "summary": "..."} | None
    """
    from config.theme_chains import resolve_sector as rs
    from llm.client import chat

    query_lower = query.lower()

    # Step 1: 精确匹配（不走LLM）
    exact_sectors = []
    keywords = [
        "光模块","光芯片","CPO","光通信","光学光电子",
        "半导体","芯片","AI芯片","存储芯片","先进封装",
        "算力","数据中心","液冷","服务器",
        "机器人","人形机器人","减速器","丝杠","传感器",
        "低空经济","飞行汽车","无人机",
        "锂电池","固态电池","钠电池","光伏","储能",
        "创新药","CRO","减肥药","医疗器械","医药",
        "汽车零部件","一体压铸","智能驾驶",
        "PCB","果链","消费电子",
    ]
    for kw in keywords:
        if kw in query_lower:
            concept, industry = rs(kw)
            if concept:
                exact_sectors.append({"name": concept, "type": "concept", "source": "keyword"})
            elif industry:
                exact_sectors.append({"name": industry, "type": "industry", "source": "keyword"})

    # 如果全部命中且没有模糊意图 → 直接返回
    fuzzy_intents = ["低位","补涨","超跌","滞涨","加速","强势","热门","龙头","机会","值得","看看"]
    has_fuzzy = any(w in query_lower for w in fuzzy_intents)
    if exact_sectors and not has_fuzzy:
        return {"sectors": exact_sectors, "summary": "关键词精确匹配"}

    # Step 2: LLM 解析
    market_ctx = _build_market_context()
    sectors_list = _build_sector_list()

    prompt = f"""把用户对股票板块的描述解析为具体的行业名。

当前市场数据:
{market_ctx}

可用的行业板块（必须从下面选）:
{chr(10).join(sectors_list[:50])}

用户问: {query}

输出JSON: {{"sectors":[{{"name":"行业名","type":"concept","reason":"为什么选这个"}}],"summary":"一句话总结"}}
规则:
- name 必须从上面"可用的行业板块"列表中选，不能自己编
- "低位/超跌/补涨" → 找B1密度高或近期跌幅大的板块
- "强势/加速" → 找趋势好的板块
- type: concept=概念板块, industry=申万行业
- 最多输出 8 个板块"""

    resp = chat([
        {"role": "system", "content": "你是A股量化分析师。输出纯JSON,不要markdown包裹。"},
        {"role": "user", "content": prompt},
    ], json_mode=True, max_tokens=1024, role="router")

    if not resp:
        # LLM 失败 → 返回精确匹配结果
        if exact_sectors:
            return {"sectors": exact_sectors, "summary": "关键词匹配(LLM不可用)"}
        return None

    try:
        content = resp["content"]
        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]
        parsed = json.loads(content.strip())
        sectors = parsed.get("sectors", [])
    except (json.JSONDecodeError, KeyError):
        return {"sectors": exact_sectors, "summary": "LLM解析失败,使用关键词匹配"} if exact_sectors else None

    # Step 3: 验证并合并
    valid_names = {r.split("(")[0] for r in sectors_list}
    validated = []
    for s in sectors:
        name = s.get("name", "")
        if name in valid_names and name not in [x["name"] for x in validated]:
            validated.append(s)
    # 合并精确匹配
    for es in exact_sectors:
        if es["name"] not in [v["name"] for v in validated]:
            validated.append(es)

    return {
        "sectors": validated,
        "summary": parsed.get("summary", ""),
    }
