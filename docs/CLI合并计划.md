# CLI 命令合并精简 Plan v2

## Context

当前 33 个命令，功能重叠、权责不明。9 条批注重定义了 CLI 的职责边界。

核心原则：
- **数据获取与计算完全分离**：`data sync` 只拉不分析，`scan` 只算不拉
- **持仓与关注列表操作完全分离**：`holdings` 管交易账户，`watch` 管选股池
- **报告不做数据拉取**：`report` 是纯功能，从数据库读已有数据

## 目标

33 → **15** 个命令。按子命令组织，每个命令权责单一。

---

## 最终 CLI 结构

### 数据层（获取数据，存数据库）

```
data sync
    kline   (--code C | --sector S | --market) [--days N]   → 只拉 K 线到 stock_daily，不算 B1
    index   [--codes ...]                                     → 指数日线到 index_daily
    calendar                                                  → 交易日历更新

quote
    --symbol C | --holdings | --watch [--index]  → 实时行情、掘金/腾讯/akshare 级联
```

**`data sync kline`**：定时任务，每天收盘后自动执行。遍历全市场股票 → `ensure_candles` → 写入 `stock_daily`。不调用 `compute_single`。

### 计算层（扫描选股，读数据库算指标）

```
scan
    (--name 板块 | --market | --codes C1,C2) [--days N]
    [--workers N] [--auto-save] [--ai]
        → 读 stock_daily 已有 K 线 → compute_single(每只)
        → 数据不足时自动 ensure_candles 补缺后重算
        → 输出 B1/缩量结果
        → --auto-save: B1→重点 watchlist, 近B1→普通 watchlist

indicator
    --symbol C [--input FILE]  → 纯指标计算，JSON 输出

suo-bao
    --symbol C [--input FILE]  → 缩爆扫描，JSON 输出
```

**`scan`**：选股引擎。输出分三类：★B1 活跃 / △近B1 (J<20) / 缩量爆发。可选 LLM 板块叙事增强（`--ai`）。

### 报告层（读数据库，生成文本）

```
report
    stock  --symbol C [--sector 板块] [--theme 产业链]   → 从 DB 读 B1+基本面+估值 → MD 报告
    sector --name 板块                                    → 从 DB 读板块成分股 scan 结果 → MD 报告

analyze
    --symbol C [--deep] [--trade buy|sell --qty N]  → 从 DB 读 K 线+B1 → LLM 解读
                                                        --deep: +基本面/筹码/行业逻辑
                                                        --trade: +交易诊断
```

**`report`**：纯功能，不拉数据不扫描。数据不足时报错："请先运行 `scan --name XXX`"。

### 账户层（交易账户操作）

```
holdings
    add/list                                    → position 表 CRUD
    report [--review|--monitor]                 → 读持仓 DB → ensure_candles → LLM 分析

trade
    add/list                                    → trade_record 表 CRUD

account-update --total X --cash Y              → account_snapshot 快照
```

### 选股池层（关注列表操作）

```
watch
    add/remove                   → CRUD
    list [--level 1|2]           → 按层级查看
    promote/demote --code C      → 升降级
    report                        → 关注列表监控 → LLM
```

**层级**：`watchlist` 表加 `level` 字段（1=重点, 2=普通）。`scan --auto-save` 自动分层入库。

### 状态机层

```
daily-review [--date D]          → 遍历 scan 结果 → B1 状态机流转
                                      watching→near_b1→b1→bought→holding→sell_candidate→sold
                                      不拉 K 线，只更新 b1_tracking 表状态

b1-tracking --code C [--limit N] → 查看某票完整状态轨迹
```

**`daily-review`**：只做状态流转。输入来自 `scan` 已算好的 `b1_candidate` / `watchlist_daily`，输出到 `b1_tracking`。

### 行业/指数/发布/搜索

```
index list                      → 已缓存指数 + 最新涨跌

industry
    rebuild  --source ths|em                    → 重建行业索引
    lookup   (--code C | --name N | --search S) → 查询行业标签
    research --topic T [--urls U] [--text B]    → Web Search + LLM 总结存档

publish --input FILE [--title T] → MD → 飞书文档
```

---

## 数据流总览

```
┌─────────────────────────────────────────────────────────────────┐
│                        数据获取层                                │
│  data sync kline  ──→ stock_daily 表                            │
│  data sync index  ──→ index_daily 表                            │
│  data sync calendar ──→ trading_calendar 表                     │
│  quote            ──→ 实时打印（不持久化）                       │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 读 K 线数据
┌─────────────────────────────────────────────────────────────────┐
│                        指标计算层                                │
│  scan            ──→ compute_single + suo_bao_scan              │
│                       结果写入 watchlist_daily / b1_candidate    │
│  indicator       ──→ compute_single → JSON 输出                 │
│  suo-bao         ──→ suo_bao_scan  → JSON 输出                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 读指标结果
┌─────────────────────────────────────────────────────────────────┐
│                        报告展现层                                │
│  report stock/sector ──→ 从 DB 读 → Markdown                    │
│  analyze            ──→ 从 DB 读 → LLM 解读 → Markdown           │
│  holdings report    ──→ 从 DB 读 → LLM 复盘/监控 → Markdown     │
│  watch report       ──→ 从 DB 读 → LLM 关注监控 → Markdown      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼ 独立并行
┌─────────────────────────────────────────────────────────────────┐
│                        独立层                                    │
│  holdings CRUD  ←→ position / trade_record / position_archive    │
│  watch CRUD     ←→ watchlist (level=1/2)                        │
│  daily-review   ←→ b1_tracking (状态机)                          │
│  b1-tracking    ←→ b1_tracking (只读查询)                        │
└─────────────────────────────────────────────────────────────────┘
```

---

## 批注逐条回应

### 1. data sync — 数据获取，不算 B1

**同意。** `data sync kline` 只调用 `ensure_candles`，不调用 `compute_single`。定位是定时任务（cron），每天收盘后跑一次。只保证 `stock_daily` 表数据完整。

```bash
python cli.py data sync kline --market        # 定时任务：拉全市场 K 线
python cli.py data sync index                  # 拉指数 K 线
python cli.py data sync calendar               # 更新交易日历
```

### 2. scan — 选股引擎

**同意。** 负责 B1 + 缩量爆发计算。数据不足时自动补缺（内部调 `ensure_candles` 再调 `compute_single`）。支持三种输入范围：

```bash
python cli.py scan --name 创新药               # 按板块
python cli.py scan --market                    # 按全市场
python cli.py scan --codes 002693,600276,000977 # 按指定列表
```

结果分层入库：B1（原始B1/超卖缩量B/回踩白线B等）→ `watchlist` level=1（重点），近B1 (J<20) → level=2（普通）。

### 3. 实时行情 — quote

```bash
python cli.py quote --symbol 002693            # 单只
python cli.py quote --holdings                  # 当前持仓批量
python cli.py quote --watch                     # 关注列表批量
python cli.py quote --index                     # 主要指数
```

数据源级联：掘金 `current()` → 腾讯 `qt.gtimg.cn` → akshare `spot_em`。非交易时段用最近收盘价，标注时间戳。

### 4. 指数数据库

新增 `index_daily` 表（结构同 `stock_daily`）：

```sql
CREATE TABLE IF NOT EXISTS index_daily (
    code  TEXT NOT NULL,   -- 000001(上证) 399001(深成指) 399006(创业板) 000688(科创50) 000300(沪深300) 000016(上证50)
    date  TEXT NOT NULL,
    open  REAL, high REAL, low REAL, close REAL, volume REAL, amount REAL,
    PRIMARY KEY (code, date)
);
```

```bash
python cli.py data sync index                    # 更新所有指数到最新
python cli.py index list                         # 查看已缓存指数
python cli.py quote --index                      # 实时指数行情（上证深成创指等）
```

默认覆盖：上证综指、深证成指、创业板指、科创50、沪深300、上证50、中证500。可通过 `--codes` 扩展。

### 5. 分层关注列表

`watchlist` 表加 `level` 字段（INTEGER DEFAULT 2）：

| level | 含义 | 触发条件 |
|-------|------|---------|
| 1 | 重点 | B1 信号触发、连续 >=3 天近B1 |
| 2 | 普通 | 近B1 (J<20)、手动加入 |

```bash
python cli.py watch promote --code 002693        # 升级为重点
python cli.py watch demote --code 300199         # 降级为普通
python cli.py watch list --level 1               # 只看重点
```

### 6. report — 纯功能

`report` 不从外部拉数据，不计算指标。只从数据库已有数据组装 Markdown。数据不足时报错。

```bash
python cli.py report stock --symbol 600707       # 个股报告（需要已有 scan 结果）
python cli.py report sector --name 创新药         # 板块报告（需要已有 scan 结果）
```

### 7. daily-review — 状态机流转

只做 `b1_candidate` → `b1_tracking` 的状态转换，不拉 K 线。去重持仓逻辑（持仓分析归 `holdings report`）。

```
遍历 b1_candidate 最新批次
  → 读取上次状态（b1_tracking 最新记录）
  → 判断状态流转规则
  → 更新 b1_tracking 表
  → 输出预警（新 B1 / B1 消失 / 进入持股 / 卖出信号）
```

### 8. 数据获取与计算分离

```
data sync    → 数据获取，只写 stock_daily / index_daily / trading_calendar
scan         → 读 stock_daily → 计算 B1/缩爆 → 写 watchlist_daily / b1_candidate
quote        → 实时行情，不持久化
report       → 读 watchlist_daily / b1_candidate → 组装文本

holdings/trade → 独立的交易记录层，不与扫描层耦合
watch          → 独立的选股池层
```

### 9. Web Search（Tavily 集成）

**方案：Tavily 内嵌，作为 LLM Background Context**

```python
# data_source/web_search.py
import os, requests

TAVILY_API_KEY = os.environ.get("TAVILY_API_KEY", "")
TAVILY_URL = "https://api.tavily.com/search"

def search_context(query: str, max_results: int = 5) -> list[dict]:
    """搜索最新信息，返回 [{title, url, content, score}]"""
    ...

def get_industry_context(sector_name: str) -> str:
    """搜索板块最新新闻/政策/催化剂 → 拼接为 LLM 上下文文本"""
    ...

def get_theme_context(theme: str) -> str:
    """搜索主线题材逻辑背景 → 拼接为 LLM 上下文文本"""
    ...
```

**存储**：搜索结果为 LLM 分析提供 Background Context，缓存到 `llm_report` 表（复用已有结构，`report_type = "web_search"`）：

| 字段 | 内容 |
|------|------|
| query_text | 原始的搜索 query |
| search_results | JSON: [{title, url, content, score, collected_at}] |
| TTL | 24 小时自动失效 |

**接入点**：
- `scan --ai` — 板块扫描前自动搜索行业近 3 天新闻，注入 LLM 叙事分析
- `analyze --deep` — 个股深度分析前搜索产业链/题材相关消息，补充基本面外的市场情绪
- `industry research` — 搜索 + LLM 总结 → 存档

**不装 Tavily 则降级**：akshare `stock_news_em`（个股新闻）/ `stock_news_main_cx`（财新快讯）。质量差但兜底。

---

## 实施

1. `watchlist` 表加 `level` 字段（ALTER TABLE）
2. 新建 `index_daily` 表
3. 新建 `data_source/web_search.py`
4. 重构 `cli.py` parser + dispatch + 旧别名
5. `scan` 去重 `data sync` 的 B1 计算部分
6. `daily-review` 简化到只做状态流转

## 向后兼容

旧命令第一阶段隐藏（打印废弃提示），第二阶段删除。映射同 v1。

## 验证

```bash
python cli.py data sync kline --market        # 只拉K线
python cli.py scan --name 创新药 --auto-save   # 算B1+入库
python cli.py quote --holdings                 # 实时行情
python cli.py data sync index                  # 指数
python cli.py index list                       # 指数列表
python cli.py watch list --level 1             # 重点列表
python cli.py report stock --symbol 600707     # 纯报告
```
