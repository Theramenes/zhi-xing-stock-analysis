"""
市场上下文构建器 — 为 LLM 深度分析提供板块定位、横向对比、市场叙事
支持两种路由：产业链映射（机器人→电机/减速器/执行器）vs 传统板块扫描
"""
import json
from data_source.registry import registry as ds_registry


def build_chain_context(theme_name: str, target_code: str = None) -> dict | None:
    """
    产业链上下文 — 使用 theme_chains 映射，精确对链条内公司
    比 SectorB1Scanner 更精准（只拉链条内 20-40 只核心标的，不用扫整个概念板块）
    """
    from config.theme_chains import resolve_theme, get_chain_peers
    name, chain = resolve_theme(theme_name)
    if not chain:
        return None

    all_codes = []
    sub_groups = {}
    for sub_name, codes in chain.items():
        all_codes.extend(codes)
        sub_groups[sub_name] = list(codes)

    # 去重
    seen = set()
    unique_codes = []
    for c in all_codes:
        if c not in seen:
            seen.add(c)
            unique_codes.append(c)

    if target_code and target_code not in unique_codes:
        unique_codes.append(target_code)

    # 拉每只票的 B1 指标
    from storage.kline_filler import ensure_candles
    from indicators.b1_calculator import compute_single

    peers = []
    for code in unique_codes:
        try:
            candles = ensure_candles(code, required_days=114)
            if len(candles) < 30:
                continue
            ind = compute_single(code, candles)
            if "error" in ind:
                continue
            # 找到该票所在的子环节
            sub = "其他"
            for sname, codes in sub_groups.items():
                if code in codes:
                    sub = sname
                    break
            peers.append({
                "code": code,
                "name": ind.get("name", code),
                "sub_group": sub,
                "J": ind.get("J"),
                "评分": ind.get("评分"),
                "趋势": ind.get("趋势"),
                "信号": ind.get("信号", []),
                "超缩量": ind.get("超缩量", False),
                "last": ind.get("last"),
                "change_pct": ind.get("change_pct", 0),
            })
        except Exception:
            pass

    # 按子环节分组
    b1_count = sum(1 for p in peers if p.get("信号") or p.get("J", 999) < 20)
    return {
        "name": name,
        "type": "产业链",
        "sub_groups": {s: [p for p in peers if p["sub_group"] == s] for s in sub_groups},
        "peers": peers,
        "total": len(peers),
        "b1_density": f"{b1_count}/{len(peers)}" if peers else "0/0",
        "target_sub": next((p["sub_group"] for p in peers if p["code"] == target_code), "?") if target_code else None,
    }


def build_sector_context(sector_name: str, target_code: str = None) -> dict | None:
    """
    拉取板块级别的上下文数据，用于 LLM 深度分析。
    返回: {"name","rank","change_pct","fund_flow","total_stocks","b1_density",
           "top_peers":[...], "market_context":{...}} 或 None
    """
    from scanning.sector_scanner import SectorOverview, SectorB1Scanner

    # 1. 板块概览（排名、资金、龙头）
    ov = SectorOverview()
    name, stype = ov.resolve(sector_name)
    overview = ov.scan(sector_name)
    if not overview or overview.total_stocks == 0:
        return None

    # 2. 板块 B1 扫描（取同板块票的指标对比）
    scanner = SectorB1Scanner(workers=10)
    combined = scanner.scan(sector_name, days=120)
    b1_result = combined.get("b1")

    # 3. 板块排名（从 iFind 获取市场排名）
    rank_str = _get_sector_rank(sector_name)
    fund_flow_str = _get_sector_fund_flow(overview)

    # 4. 同板块 B1 对比
    top_peers = []
    if b1_result:
        stocks = b1_result.stocks
        # 按评分降序排列
        sorted_stocks = sorted(stocks, key=lambda s: (len(getattr(s, '信号', []) or []), getattr(s, '评分', 0)), reverse=True)
        for s in sorted_stocks[:10]:
            top_peers.append({
                "code": getattr(s, 'code', '?'),
                "name": getattr(s, 'name', '?'),
                "J": getattr(s, 'J', '?'),
                "评分": getattr(s, '评分', '?'),
                "趋势": getattr(s, '趋势', '?'),
                "信号": getattr(s, '信号', []) if hasattr(s, '信号') else [],
            })

    # 5. B1 密度
    b1_count = len(b1_result.b1_stocks) if b1_result else 0
    near_count = len(b1_result.near_b1_stocks) if b1_result else 0
    total = overview.total_stocks
    b1_density = f"{b1_count}/{total} ({b1_count/total*100:.0f}%)" if total else "?"

    # 6. 市场环境（领涨板块、市场宽度）
    market_ctx = _get_market_snapshot()

    return {
        "name": sector_name,
        "rank": rank_str,
        "change_pct": _avg_change(overview),
        "fund_flow": fund_flow_str,
        "total_stocks": total,
        "b1_density": b1_density,
        "top_peers": top_peers,
        "market_context": market_ctx,
    }


def _get_sector_rank(sector_name: str) -> str:
    """获取板块在行业中的排名"""
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        return "?"
    try:
        payload = json.dumps(
            {"searchstring": "行业板块涨跌幅排行", "searchtype": "plate"},
            ensure_ascii=False,
        )
        data = ifind._call("endpoint-call", "--name", "a_share_common_query",
                           "--payload", payload, timeout=30)
        if not data or not data.get("ok"):
            return "?"
        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return "?"
        tb = tables[0].get("table", {})
        names = [str(n) for n in tb.get("板块名称", [])]
        changes = tb.get("涨跌幅", [])
        for i, n in enumerate(names):
            if sector_name[:3] in n or n in sector_name:
                chg = changes[i] if i < len(changes) else 0
                return f"第{i+1}名 / 共{len(names)}个行业 (涨跌{chg})"
        return f"未进入排行榜前{len(names)}"
    except Exception:
        return "?"


def _get_sector_fund_flow(overview) -> str:
    """从板块概览提取资金流向"""
    if not overview or not overview.groups:
        return "?"
    total_flow = 0
    for g in overview.groups.values():
        total_flow += getattr(g, 'total_fund_flow', 0) or 0
    if abs(total_flow) >= 1e8:
        return f"{total_flow/1e8:+.1f}亿"
    if abs(total_flow) >= 1e4:
        return f"{total_flow/1e4:+.0f}万"
    return f"{total_flow}"


def _avg_change(overview) -> float:
    """板块平均涨跌"""
    if not overview or not overview.stocks:
        return 0
    changes = [getattr(s, 'change_pct', 0) or 0 for s in overview.stocks[:20]]
    return sum(changes) / len(changes) if changes else 0


def _get_market_snapshot() -> dict:
    """市场快照：领涨板块 + 市场宽度"""
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        return {"top_sectors": "?", "market_breadth": "?"}
    try:
        payload = json.dumps(
            {"searchstring": "行业板块涨跌幅排行", "searchtype": "plate"},
            ensure_ascii=False,
        )
        data = ifind._call("endpoint-call", "--name", "a_share_common_query",
                           "--payload", payload, timeout=30)
        if not data or not data.get("ok"):
            return {"top_sectors": "?", "market_breadth": "?"}
        tables = data.get("data", {}).get("tables", [])
        if not tables:
            return {"top_sectors": "?", "market_breadth": "?"}
        tb = tables[0].get("table", {})
        names = [str(n) for n in tb.get("板块名称", [])]
        changes = tb.get("涨跌幅", [])
        top5 = []
        up_count = 0
        for i in range(min(15, len(names))):
            chg = changes[i] if i < len(changes) else 0
            if isinstance(chg, (int, float)) and chg > 0:
                up_count += 1
            if i < 5:
                top5.append(f"{names[i]}({chg:+.1f}%)" if isinstance(chg, (int, float)) else f"{names[i]}")
        breadth = f"前15行业 {up_count}涨/{15-up_count}跌"
        return {
            "top_sectors": "、".join(top5),
            "market_breadth": breadth,
        }
    except Exception:
        return {"top_sectors": "?", "market_breadth": "?"}
