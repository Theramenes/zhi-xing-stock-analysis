# 知行股票分析系统 CLI 完整文档

> 共 33 个子命令 | 最后更新：2026-06-02

---

## 一、全流程 CLI（16 个）

用户一键触发，自动走完整业务闭环。统一入口：`ensure_candles` → `compute_single` → 输出。

### 数据扫描类

| 命令 | 概述 | 核心流程 | 参数 |
|------|------|---------|------|
| `kline-update` | 全市场/板块/单只 K 线 + B1 扫描 | 获取代码列表 → 逐只 ensure_candles → compute_single → 入库关注 | `--code/-c` \| `--all` \| `--market` \| `--sector/-s` \| `--days` (114) \| `--add-watchlist` |
| `scan-sector-b1` | 板块 B1 扫描 | 概览 + 逐只 K 线 + 指标 → 报告 → 自动入库 watchlist | `--name/-n`(必填) \| `--output/-o` \| `--workers`(20) \| `--days`(120) \| `--no-cache` \| `--no-auto-save` \| `--publish/--no-publish` |
| `scan-sector-overview` | 板块概览 | 走势/资金/龙头/异动 → 报告/飞书 | `--name/-n`(必填) \| `--output/-o` \| `--publish/--no-publish` |
| `scan-market` | 全市场扫描 | 遍历板块 → 逐板块扫 → 汇总报告 | `--output/-o` \| `--workers`(20) \| `--days`(120) \| `--no-cache` \| `--max-sectors`(0=全部) |
| `daily-review` | 日终追踪 | 拉 K 线 → 算指标 → 状态转换（B1 状态机）→ 预警 | `--date` \| `--sector`(额外板块) \| `--workers`(10) \| `--output/-o`(JSON) |

### LLM 增强类（需 `ZX_LLM_API_KEY`）

| 命令 | 概述 | 核心流程 | 参数 |
|------|------|---------|------|
| `llm-stock` | 个股 AI 技术解读 | ensure_candles → B1 → LLM；可选 `--sector` 触发三层深度分析（个股+板块定位+大局研判） | `--symbol/-s`(必填) \| `--days`(114) \| `--sector` |
| `llm-sector` | 板块 AI 叙事增强 | 板块扫描 → LLM 叙事分析 | `--name/-n`(必填) \| `--workers`(20) \| `--days`(120) |
| `holdings-letter` | 持仓日报（分析师口吻 + 次日建议） | 持仓 K 线 → B1 → LLM 口吻 | `--output/-o` |
| `holdings-review` | 持仓复盘/监控 | 复盘模式：当前持仓+今日已清仓+调仓对比+交易流水 → LLM 分析操作得失。监控模式：只看当前持仓 B1 状态 | `--date`(今天) \| `--mode`(auto/review/monitor) \| `--output/-o` |
| `watchlist-report` | 关注列表监控报告 | watchlist_daily 已有快照 → LLM 总结变化 | `--output/-o` |
| `trade-diagnosis` | 交易前 AI 诊断 | K 线 + B1 + 持仓上下文 → LLM 建议 | `--symbol/-s`(必填) \| `--name` \| `--action`(buy/sell 必填) \| `--shares`(必填) \| `--days`(114) |
| `industry-research` | 行业研究 | URL/文本/stdin → LLM 总结行业逻辑 → 保存到 `references/industry_logic/` | `--topic/-t`(必填) \| `--urls/-u` \| `--text` \| `--stdin` \| `--output/-o` |

### 数据报告生成类

| 命令 | 概述 | 核心流程 | 参数 |
|------|------|---------|------|
| `kline-analyze` | K 线形态+基本面+题材+B1 综合分析（LLM） | ensure_candles → B1 → 基本面 → 筹码 → 产业链上下文 → LLM；可选 `--verify` 双源交叉验证 | `--symbol/-s`(必填) \| `--name` \| `--theme` \| `--days`(114) \| `--verify` \| `--output/-o` |
| `data-report` | 个股完整数据报告 | B1 + 基本面 + 估值 + 消息面 + 筹码 + 资金流 + 市场大局整合 | `--symbol/-s`(必填) \| `--name` \| `--sector` \| `--theme` \| `--output/-o` \| `--days`(114) |
| `sector-report` | 板块扫描数据报告 | 扫描 + 市场大局 → 整合报告（龙头+B1+领涨+基本面） | `--name/-n`(必填) \| `--output/-o` \| `--workers`(20) \| `--days`(120) |

---

## 二、模块/CRUD CLI（17 个）

操作特定数据表/模块，短调用链。

### 持仓 & 交易

| 命令 | 概述 | 操作表 | 参数 |
|------|------|--------|------|
| `holdings-add` | 新增或更新持仓 | `position` | `--code/-c`(必填) \| `--name/-n` \| `--cost`(必填) \| `--qty`(必填) \| `--strategy` \| `--notes` \| `--stop-loss` \| `--target` |
| `holdings-list` | 列出当前持仓 + 30 天盈亏汇总 | `position` | `--verbose/-v` |
| `transaction-add` | 新增交易流水（自动更新持仓成本/数量） | `trade_record` + `position` | `--code/-c`(必填) \| `--date`(今天) \| `--direction`(必填: buy/sell/t_buy/t_sell/clear) \| `--qty`(必填) \| `--price`(必填) \| `--reason` \| `--memo` |
| `transaction-list` | 查看交易流水 | `trade_record` | `--code/-c` \| `--days`(90) \| `--limit`(100) |

### 关注 & 追踪

| 命令 | 概述 | 操作表 | 参数 |
|------|------|--------|------|
| `watchlist-add` | 加入关注列表 | `watchlist` | `--code/-c`(必填) \| `--name/-n` \| `--reason/-r` \| `--priority`(3) \| `--tags`(JSON) \| `--price` \| `--notes` |
| `watchlist-list` | 查看关注列表 | `watchlist` | `--status`(active/observing/archived/all) |
| `watchlist-remove` | 移出关注列表（软删除） | `watchlist` | `--code/-c`(必填) \| `--reason/-r` |
| `b1-tracking` | 查看 B1 状态追踪历史 | `b1_tracking` | `--code/-c`(必填) \| `--limit`(30) |

### 板块 & 账户

| 命令 | 概述 | 操作表 | 参数 |
|------|------|--------|------|
| `focus-sector-add` | 添加重点板块 | `focus_sector` | `--name/-n`(必填) \| `--type`(industry/concept) \| `--source` \| `--priority`(3) \| `--notes` \| `--tags`(JSON) |
| `focus-sector-list` | 查看重点板块 | `focus_sector` | `--status`(active) |
| `sector-update` | 更新东财板块成分股缓存 | `sector_stock` | `--name/-n` \| `--type`(concept/industry) \| `--all` |
| `account-update` | 更新账户快照 | `account_snapshot` | `--total`(必填) \| `--cash`(必填) \| `--position-ratio` \| `--pnl` |

### 指标 & 发布

| 命令 | 概述 | 核心流程 | 参数 |
|------|------|---------|------|
| `indicator` | 计算知行指标（B1/KDJ/RSI/趋势等） | JSON 解析 → `compute_single` → JSON 输出 | `--symbol/-s` \| `--input/-i`(K线JSON) |
| `suo-bao` | 缩爆 B1 扫描 | JSON 解析 → `suo_bao_scan` → JSON 输出 | `--symbol/-s` \| `--input/-i` \| `--D`(5) \| `--S`(0.75) \| `--V`(3) \| `--N`(0.2) |
| `report` | 从原始 JSON 生成报告 | JSON → 重建扫描对象 → 生成 MD 报告 | `--input/-i`(必填) \| `--output/-o` |
| `publish` | 发布报告到飞书 | MD 文件 → 飞书 API → 飞书文档 URL | `--input/-i`(必填) \| `--title` \| `--folder` |
| `industry-rebuild` | 重建行业分类索引（同花顺/东财） | 调 iFind 或 akshare → 写本地索引 | `--source/-s`(必填: ths/em) |
| `industry-lookup` | 查询行业标签（个股→行业 / 行业→成分股） | 查本地索引 | `--code/-c` \| `--name/-n` \| `--source`(ths/em) \| `--search` |

---

## 三、统一入口 & 数据链路

### K 线获取（所有行情命令共用）

```
ensure_candles(code, 114)
  → KlineFetchCoordinator.fetch_kline(code, 114)
      ├── db.ensure_trading_calendar()  ← 四级降级(sina→iFind→baostock→日历)
      ├── compute_start_date()          ← 唯一一处交易日反推
      ├── _cascade_fetch()              ← 多源级联(掘金→腾讯→baostock)
      └── _iterative_backfill()         ← 停牌/新股自动补缺
```

### 多源级联优先级

```
iFind(付费HTTP) → 掘金myquant → 腾讯fqkline → 东财直连 → efinance → akshare → baostock → SQLite
 快速路径无熔断     免费最优先      免费主力       备选         降级      降级       兜底     本地缓存
```

### B1 指标计算

```
compute_single(code, candles)
  → StockAnalyzer._compute()
      ├── KDJ(9,3,3) → J值
      ├── RSI(3) / MACD
      ├── 知行趋势线(白线/黄线/BBI)
      ├── 单针下20 / 缩量分级 / 振幅异动
      ├── 7种B1买点判定(原始B1/超卖缩量B/回踩白线B/...)
      └── return {J, RSI, 趋势, 评分, 信号, 超缩量, 洗盘异动, ...}
```

### 综合数据聚合（kline-analyze / data-report）

```
ensure_candles → compute_single
  → get_fundamentals()       # 基本面级联
  → get_valuation()          # PE/PB 历史分位
  → get_chip()               # 筹码分布
  → get_fund_flow()          # 资金流
  → get_market_context()     # 市场大局（涨跌比/成交量）
  → build_sector_context()   # 板块定位
  → build_chain_context()    # 产业链对标 (theme_chains.py)
```

---

## 四、断点续扫

`kline-update --market` 内部逻辑：

```
ensure_candles(code, days)
  ├── 查 stock_daily 表：已有 >=30 天 → 从 SQLite 返回（秒跳过）
  ├── 查 stock_daily 表：<30 天 → 走外部源拉取+补缺
  └── 写入 SQLite 缓存
```

中断后重跑同一命令，已处理的票秒跳过，只处理未完成的。**不需要手动记录进度。**

---

## 五、B1 状态机

```
watching → near_b1(J<20) → b1(有信号) → bought(用户买入) → holding
   ↑          │                │               │
   └──(7天)───┘                ↓               ↓
                        observing ←(B1消失)─┘
                                                ↓
                                    sell_candidate → sold
```

9 状态流转，`daily-review` 命令自动更新。`b1-tracking --code` 查看任意票完整轨迹。

---

## 六、常用操作速查

```bash
# 持仓管理
python cli.py holdings-add --code 002460 --cost 45.2 --qty 1000 --strategy 长线
python cli.py holdings-list --verbose
python cli.py transaction-add --code 002460 --direction sell --price 48.0 --qty 500 --reason 止盈
python cli.py holdings-review                          # 持仓复盘(LLM)
python cli.py holdings-letter                          # 持仓日报(LLM)

# 全市场扫描(断点续扫, B1自动入关注)
python cli.py kline-update --market --add-watchlist --days 114

# 板块扫描
python cli.py sector-update --name 光模块               # 先缓存成分股
python cli.py kline-update --sector 光模块               # 扫描板块
python cli.py scan-sector-b1 --name 创新药               # 板块B1完整流程

# 个股分析
python cli.py llm-stock --symbol 002693 --days 114       # AI解读
python cli.py kline-analyze --symbol 000977 --theme 算力 # K线+题材综合分析
python cli.py data-report --symbol 600707 --output rpt.md # 完整数据报告
python cli.py trade-diagnosis --symbol 002693 --action buy --shares 500  # 交易前诊断

# 数据维护
python cli.py sector-update --all                        # 刷新全部东财板块缓存
python cli.py kline-update --code 002693                  # 单只补缺
python cli.py daily-review --sector 医药生物              # 日终追踪
```

---

## 七、分类矩阵

| # | 命令 | 全流程 | 需外部数据 | 需 LLM | 修改 DB |
|---|------|:---:|:---:|:---:|:---:|
| 1 | indicator | | | | |
| 2 | suo-bao | | | | |
| 3 | scan-sector-overview | ✓ | ✓ | | ✓* |
| 4 | scan-sector-b1 | ✓ | ✓ | | ✓* |
| 5 | scan-market | ✓ | ✓ | | |
| 6 | report | | | | |
| 7 | publish | | ✓(飞书) | | |
| 8 | holdings-add | | | | ✓ |
| 9 | holdings-list | | | | |
| 10 | transaction-add | | | | ✓ |
| 11 | transaction-list | | | | |
| 12 | watchlist-add | | | | ✓ |
| 13 | watchlist-list | | | | |
| 14 | watchlist-remove | | | | ✓ |
| 15 | daily-review | ✓ | ✓ | | ✓ |
| 16 | b1-tracking | | | | |
| 17 | focus-sector-add | | | | ✓ |
| 18 | focus-sector-list | | | | |
| 19 | llm-stock | ✓ | ✓ | ✓ | |
| 20 | llm-sector | ✓ | ✓ | ✓ | |
| 21 | holdings-letter | ✓ | ✓ | ✓ | |
| 22 | holdings-review | ✓ | ✓ | ✓ | |
| 23 | watchlist-report | ✓ | | ✓ | |
| 24 | trade-diagnosis | ✓ | ✓ | ✓ | |
| 25 | account-update | | | | ✓ |
| 26 | industry-rebuild | | ✓ | | ✓ |
| 27 | industry-lookup | | | | |
| 28 | industry-research | ✓ | ✓(URL) | ✓ | ✓** |
| 29 | kline-analyze | ✓ | ✓ | ✓ | |
| 30 | data-report | ✓ | ✓ | | |
| 31 | sector-report | ✓ | ✓ | | |
| 32 | kline-update | ✓ | ✓ | | ✓ |
| 33 | sector-update | | ✓ | | ✓ |

> `✓*` = 自动入库 watchlist（可通过 `--no-auto-save` 禁用）
> `✓**` = 写入文件 `references/industry_logic/`，不写 DB
