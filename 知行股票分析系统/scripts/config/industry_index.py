"""
行业分类双体系索引 — 同花顺(iFind) + 东方财富(akshare/efinance)
双向存储: industry → stocks 和 stock → tags

用法:
    python cli.py industry-rebuild --source ths     # iFind构建同花顺索引
    python cli.py industry-rebuild --source em      # akshare构建东财索引
    python cli.py industry-lookup --code 002463      # 查个股标签
    python cli.py industry-lookup --name 电池        # 查行业成分股
"""
import json
import os
import time
import random
from typing import List, Dict, Optional

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data")
THS_PATH = os.path.join(DATA_DIR, "industry_index_ths.json")
EM_PATH = os.path.join(DATA_DIR, "industry_index_em.json")

INDEX_PATHS = {"ths": THS_PATH, "em": EM_PATH}


# ============================================================
# 构建
# ============================================================

def rebuild_ths_index() -> dict:
    """同花顺体系 — iFind 构建"""
    from data_source.registry import registry as ds_registry
    ifind = ds_registry.get_source("ifind")
    if not ifind or not ifind.is_available():
        print("[ths] iFind 不可用")
        return _empty_index("ths")

    import json as _json
    industry_names = []
    concept_names = []

    # 1. 行业板块列表
    for plate_type, target in [("行业", "行业板块涨跌幅排行"), ("概念", "概念板块涨跌幅排行")]:
        try:
            payload = _json.dumps({"searchstring": target, "searchtype": "plate"}, ensure_ascii=False)
            data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=30)
            if data and data.get("ok"):
                tables = data.get("data", {}).get("tables", [])
                if tables:
                    tb = tables[0].get("table", {})
                    names = [str(n) for n in tb.get("板块名称", [])]
                    if plate_type == "行业":
                        industry_names = names
                    else:
                        concept_names = names
                    print(f"[ths] {plate_type}: {len(names)} 个")
        except Exception as e:
            print(f"[ths] {plate_type}列表: {e}")

    all_names = industry_names + concept_names
    print(f"[ths] 共 {len(all_names)} 个板块")

    # 2. 逐板块拉成分股
    stock_tags: Dict[str, dict] = {}
    industry_map: Dict[str, dict] = {}

    for i, name in enumerate(all_names):
        try:
            # 成分股查询
            payload = _json.dumps(
                {"searchstring": f"{name} 成分股 股票代码 股票简称", "searchtype": "stock"},
                ensure_ascii=False)
            data = ifind._call("endpoint-call", "--name", "a_share_common_query", "--payload", payload, timeout=30)
            if not data or not data.get("ok"):
                continue
            tables = data.get("data", {}).get("tables", [])
            if not tables:
                continue
            tb = tables[0].get("table", {})
            codes = tb.get("股票代码", [])
            names_col = tb.get("股票简称", [])
            members = []
            for j in range(min(len(codes), len(names_col))):
                code = str(codes[j]).split(".")[0]
                sname = str(names_col[j])
                if code and len(code) == 6:
                    members.append(code)
                    if code not in stock_tags:
                        stock_tags[code] = {"name": sname, "tags": []}
                    stock_tags[code]["tags"].append(name)
            industry_map[name] = {"stocks": members, "count": len(members)}
        except Exception:
            continue
        if (i + 1) % 50 == 0:
            print(f"  {i+1}/{len(all_names)}...")

    index = {
        "source": "ths", "updated": time.strftime("%Y-%m-%d %H:%M"),
        "industries": industry_map, "stocks": stock_tags,
        "total_industries": len(industry_map), "total_stocks": len(stock_tags),
    }
    _save_index(index, "ths")
    return index


def rebuild_em_index() -> dict:
    """东方财富体系 — akshare 构建"""
    try:
        import akshare as ak
    except ImportError:
        print("[em] akshare 未安装")
        return _empty_index("em")

    # 1. 行业 + 概念列表
    all_names = []
    for fn, label in [(ak.stock_board_industry_name_em, "行业"),
                       (ak.stock_board_concept_name_em, "概念")]:
        try:
            time.sleep(random.uniform(1, 3))
            df = fn()
            if df is not None and not df.empty:
                names = df["板块名称"].tolist()
                all_names.extend(names)
                print(f"[em] {label}: {len(names)} 个")
        except Exception as e:
            print(f"[em] {label}列表: {e}")

    print(f"[em] 共 {len(all_names)} 个板块")

    # 2. 逐板块拉成分股
    stock_tags: Dict[str, dict] = {}
    industry_map: Dict[str, dict] = {}

    for i, name in enumerate(all_names):
        try:
            time.sleep(random.uniform(0.5, 1.5))
            # 先试行业接口
            df = None
            try:
                df = ak.stock_board_industry_cons_em(symbol=name)
            except Exception:
                pass
            if df is None or df.empty:
                try:
                    df = ak.stock_board_concept_cons_em(symbol=name)
                except Exception:
                    pass
            if df is None or df.empty:
                continue

            code_col = "代码" if "代码" in df.columns else df.columns[0]
            name_col = "名称" if "名称" in df.columns else df.columns[1]
            members = []
            for _, row in df.iterrows():
                code = str(row[code_col])
                sname = str(row[name_col])
                if code and len(code) == 6:
                    members.append(code)
                    if code not in stock_tags:
                        stock_tags[code] = {"name": sname, "tags": []}
                    stock_tags[code]["tags"].append(name)
            industry_map[name] = {"stocks": members, "count": len(members)}
        except Exception:
            continue
        if (i + 1) % 20 == 0:
            print(f"  {i+1}/{len(all_names)}...")

    index = {
        "source": "em", "updated": time.strftime("%Y-%m-%d %H:%M"),
        "industries": industry_map, "stocks": stock_tags,
        "total_industries": len(industry_map), "total_stocks": len(stock_tags),
    }
    _save_index(index, "em")
    return index


# ============================================================
# 查询
# ============================================================

def load_index(source: str = "ths") -> dict:
    """加载已缓存的行业索引"""
    path = INDEX_PATHS.get(source, THS_PATH)
    if os.path.exists(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return _empty_index(source)


def get_tags(code: str, source: str = "ths") -> List[str]:
    """查个股的行业标签"""
    idx = load_index(source)
    stock = idx.get("stocks", {}).get(code, {})
    return stock.get("tags", [])


def get_stock_name(code: str, source: str = "ths") -> str:
    """查个股名称"""
    idx = load_index(source)
    stock = idx.get("stocks", {}).get(code, {})
    return stock.get("name", "")


def get_stocks_by_industry(name: str, source: str = "ths") -> List[str]:
    """查行业成分股"""
    idx = load_index(source)
    ind = idx.get("industries", {}).get(name, {})
    return ind.get("stocks", [])


def search_industry(keyword: str, source: str = "ths") -> List[str]:
    """模糊搜索行业名"""
    idx = load_index(source)
    return [k for k in idx.get("industries", {}) if keyword in k]


def get_industry_path(code: str, source: str = "ths") -> str:
    """个股完整行业路径"""
    tags = get_tags(code, source)
    return " > ".join(tags) if tags else "未知"


# ============================================================
# 内部
# ============================================================

def _save_index(index: dict, source: str):
    os.makedirs(DATA_DIR, exist_ok=True)
    path = INDEX_PATHS.get(source, THS_PATH)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"[{source}] 索引已保存: {path}")
    print(f"  行业数: {index.get('total_industries',0)}, 个股: {index.get('total_stocks',0)}")


def _empty_index(source: str) -> dict:
    return {"source": source, "industries": {}, "stocks": {}, "total_industries": 0, "total_stocks": 0, "updated": ""}
