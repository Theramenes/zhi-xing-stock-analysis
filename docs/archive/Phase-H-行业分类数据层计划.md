# Phase H: 行业分类双体系 + 扫描解耦

## 背景

当前板块扫描写死 iFind，iFind 挂了全部不可用。且行业分类存在两套体系：

| 体系 | 来源 | 行业数 | 特点 |
|------|------|--------|------|
| **同花顺行业分类** | iFind `a_share_common_query` | 86 个行业 + 389+ 概念 | 贴近市场认知，颗粒度细，有概念板块 |
| **申万/东财行业分类** | akshare `stock_board_industry_name_em` / efinance | 86 个行业（东财版） | 免费可用，学术标准，无概念板块 |

同一只股票在两个体系下分类可能不同（如"电池" vs "电力设备-电池"）。不能简单级联替换。

## 方案

**保存两套独立的行业分类索引**。扫描时用户/系统选择用哪套，默认优先同花顺（iFind 可用时），不可用时降级东财。

### 索引结构

两份 JSON，存储在 `data/` 下：

```
data/
├── industry_index_ths.json   # 同花顺行业分类（iFind 构建）
└── industry_index_em.json    # 东方财富行业分类（akshare/efinance 构建）
```

每份结构：

```json
{
  "source": "ths|em",
  "updated": "2026-05-28",
  "industries": {
    "电池": {
      "stocks": ["300750", "002460", ...],
      "count": 45
    },
    "机器人概念": {
      "stocks": ["300124", "002472", ...],
      "count": 380
    }
  },
  "stocks": {
    "300750": {
      "name": "宁德时代",
      "tags": ["电池", "新能源汽车", "储能"]
    }
  },
  "total_industries": 200,
  "total_stocks": 5500
}
```

双向索引：`industry → stocks` 和 `stock → tags`。

### 同花顺体系构建（iFind 可用时）

**源**：iFind `a_share_common_query`
- 行业列表：`smart-query "行业板块涨跌幅排行"` → 取板块名称
- 概念列表：`smart-query "概念板块涨跌幅排行"` → 取板块名称
- 成分股：`smart-query "{板块} 成分股 股票代码 股票简称"` → 逐个拉取
- 构建 `industry_index_ths.json`

**触发**：`python cli.py industry-rebuild --source ths`

### 东方财富体系构建（始终可用）

**源**：akshare（主）→ efinance（降）

- 行业列表：`ak.stock_board_industry_name_em()` → 板块名称
- 概念列表：`ak.stock_board_concept_name_em()` → 板块名称
- 成分股：`ak.stock_board_industry_cons_em(symbol="板块名")` + `ak.stock_board_concept_cons_em(symbol="概念名")`
- 降级：akshare 挂了 → `efinance.stock.get_realtime_quotes(["行业板块"])` 只拿排行，成分股不可用
- 构建 `industry_index_em.json`

**触发**：`python cli.py industry-rebuild --source em`

### 板块扫描解耦

`scanning/sector_scanner.py` 的 `_get_members()` 不再写死 iFind：

```
_get_members(sector_name, stype):
  1. 先查本地索引（industry_index_ths.json 或 industry_index_em.json）
  2. 索引未命中 → iFind get_sector_members → freeStockLine → akshare
  3. 返回 List[StockInfo]
```

`SectorOverview.scan()` — 概览数据只能走在线源（需要涨跌/资金流），iFind 不可用时降级 efinance。

## 实施步骤

### H1: 行业索引构建器 (1.5h)

`scripts/config/industry_index.py`：
- `rebuild_ths_index()` — iFind → 行业+概念列表 → 逐板块拉成分股 → 保存 `industry_index_ths.json`
- `rebuild_em_index()` — akshare → 同上 → 保存 `industry_index_em.json`
- `load_index(source="ths")` — 加载已缓存索引
- `get_stocks_by_industry(name, source="ths")` → `List[str]`
- `get_tags(code, source="ths")` → `List[str]`
- `search_industry(keyword, source="ths")` → `List[str]`（模糊搜索行业名）

### H2: CLI 命令 (0.5h)

```bash
python cli.py industry-rebuild --source ths     # iFind 构建同花顺索引
python cli.py industry-rebuild --source em      # akshare 构建东财索引
python cli.py industry-lookup --code 002463      # 查个股标签
python cli.py industry-lookup --name 电池        # 查行业成分股
```

### H3: sector_scanner 解耦 (1h)

- `_get_members()` → 先查本地索引 → iFind → free → akshare
- `SectorOverview.scan()` → iFind 不可用时走 efinance 概览

### H4: 数据报告集成 (0.5h)

- `data-report --symbol 002463` 展示行业标签
- `kline-analyze --theme PCB` 自动匹配到行业分类

## 关键文件

| 文件 | 作用 |
|------|------|
| `config/industry_index.py` | 双体系索引构建 + 查询 |
| `data/industry_index_ths.json` | 同花顺分类缓存 |
| `data/industry_index_em.json` | 东财分类缓存 |
| `scanning/sector_scanner.py` | `_get_members` 先查本地索引 |
| `llm/market_context.py` | 市场快照走 sector_cascade |

## 验证

- `python cli.py industry-rebuild --source em` 生成 `industry_index_em.json`，含 86 个行业 + 200+ 概念
- `python cli.py industry-lookup --code 002463` 输出 `["印制电路板", "AI服务器", ...]`
- iFind 熔断状态下 `python cli.py scan-sector-b1 --name 电池` 不报错，走东财索引找到成分股
