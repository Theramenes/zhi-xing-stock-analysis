# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

知行股票分析系统（简称「知行系统」），基于知行超级B1、单针下20、知行趋势线等自研指标的 A 股量化分析 CLI 工具。覆盖板块概览、板块B1扫描、全市场扫描、持仓管理、关注追踪、B1状态机、日终复盘。

Skill 目录结构：

```
知行交易分析系统Skill/           ← Skill 顶层（有独立 .git）
├── SKILL.md                     ← Skill 安装说明
├── docs/                        ← 设计文档（架构/Phase计划/测试指南）
├── tests/                       ← pytest 测试套件
└── 知行股票分析系统/             ← 本目录（Skill 实际代码）
    └── scripts/
```

## 开发环境

### 依赖

```bash
# 核心（必须）
pip install requests pandas

# 多源级联（免费 K 线兜底）
pip install akshare efinance baostock

# LLM 增强（可选）
pip install openai

# 测试
pip install pytest
```

### 外部数据源（必须在同级目录克隆）

```bash
cd 知行交易分析系统Skill/..
git clone https://github.com/Etherstrings/tonghuashun-ifind-skill ifind-skill
git clone https://github.com/Etherstrings/freeStockLIneskill freestock-skill
```

`scripts/data_source/config.py` 自动检测路径。

### iFind Token 配置（必须）

```bash
python ../ifind-skill/tonghuashun-ifind-skill/scripts/ifind_cli.py \
  auth-set-refresh-token --refresh-token <你的refresh_token>
```

### LLM 增强（可选，Phase F）

环境变量：

```bash
ZX_LLM_BASE_URL=https://api.anthropic.com/v1   # API endpoint
ZX_LLM_API_KEY=<your-key>                       # API Key
ZX_LLM_MODEL=claude-sonnet-4-6                  # 模型名
ZX_LLM_THINKING=true                            # 开启思考模式
ZX_LLM_THINK_BUDGET=4096                        # 思考 token 预算
```

### 飞书发布（可选）

```bash
npm install -g feishu-mcp
# 环境变量: FEISHU_APP_ID / FEISHU_APP_SECRET / FEISHU_AUTH_TYPE=user
```

## 常用命令

```bash
# === 板块扫描 ===
python scripts/cli.py scan-sector-overview --name 电池          # 板块概览（不扫个股）
python scripts/cli.py scan-sector-b1 --name 电池                # 板块B1扫描（默认自动入库到关注列表）
python scripts/cli.py scan-sector-b1 --name 电池 --no-auto-save # 仅出报告，不入库
python scripts/cli.py scan-market --max-sectors 10              # 全市场扫描

# === 单股指标 ===
python scripts/cli.py indicator --symbol 603206 --input candles.json
python scripts/cli.py suo-bao --symbol 603206 --input candles.json

# === 持仓管理 ===
python scripts/cli.py holdings-add --code 002460 --cost 45.2 --qty 1000 --strategy 长线
python scripts/cli.py holdings-list [--verbose]
python scripts/cli.py transaction-add --code 002460 --direction buy --price 45.2 --qty 500 --reason B1信号
python scripts/cli.py transaction-list [--code 002460] [--days 90]

# === 关注列表 ===
python scripts/cli.py watchlist-add --code 300750 --reason 板块龙头 --priority 1
python scripts/cli.py watchlist-list [--status active|observing|archived]
python scripts/cli.py watchlist-remove --code 300750 --reason 已建仓

# === 日终追踪（拉K线→算指标→状态转换→预警）===
python scripts/cli.py daily-review [--sector 电池,锂电池] [--workers 10]
python scripts/cli.py b1-tracking --code 002460 [--limit 30]

# === 重点板块 ===
python scripts/cli.py focus-sector-add --name 电池 --priority 1
python scripts/cli.py focus-sector-list

# === 飞书 ===
python scripts/cli.py publish --input report.md --title "电池B1扫描"
python scripts/cli.py scan-sector-b1 --name 电池 --no-publish   # 仅本地

# === 测试 ===
pytest tests/ -v
pytest tests/test_portfolio.py -v
```

## 架构总览

```
触发层             数据层               指标层           追踪/存储层          报告层           输出层
cli.py          → data_source/       → indicators/    → tracking/         → reporting/     → 飞书文档
cron/GitHub       (iFind→free→        b1_calculator    state_machine       generator       本地MD
Actions           akshare→SQLite)      suo_bao_b1      daily_review        feishu_publisher JSON摘要
                                                       storage/portfolio_db
                                                       storage/db.py
                                                  ⇅
                                           llm/enhancer (Phase F, 可选)
```

### 模块职责

| 模块 | 路径 | 职责 |
|------|------|------|
| CLI 入口 | `scripts/cli.py` | 18个子命令分发 |
| 指标计算 | `scripts/indicators/` | `b1_calculator.py`（4套指标）、`suo_bao_b1.py`（缩爆）、`valuation.py`（估值） |
| 数据源层 | `scripts/data_source/` | 抽象基类 + iFind/Free/Cache 降级链路 + `akshare_data/`（chip/financial/market/news/valuation） |
| 扫描引擎 | `scripts/scanning/` | `sector_scanner.py`（SectorOverview + SectorB1Scanner）、`industry_analyzer.py` |
| 本地数据库 | `scripts/storage/` | `db.py`（14张表）、`kline_filler.py`（按需补缺）、`portfolio_db.py`（业务CRUD）、`daily_update.py`（三层日更） |
| 日终追踪 | `scripts/tracking/` | `state_machine.py`（9状态流转）、`daily_review.py`（拉K线→算指标→状态转换→预警） |
| 报告生成 | `scripts/reporting/` | `generator.py`（Markdown）、`feishu_publisher.py`（飞书文档）、`data_report.py`（数据报告） |
| 多源级联 | `scripts/data_source/kline_cascade.py` | `KlineCascade`（6级降链：iFind→Efinance→Akshare→Free→Baostock→SQLite）、`fetchers/`（3个免费 K线 Fetcher） |
| LLM 增强 | `scripts/llm/` | `client.py`（OpenAI-compatible）、`enhancer.py`（缓存到 `llm_report` 表）、`prompts/`（6套Prompt模板） |
| 行业链 | `scripts/config/theme_chains.py` | 用户说"机器人/低空经济"时自动映射到子行业和标的 |
| 黑名单 | `scripts/config/blacklist.py` | 688/920/8/ST 过滤 |

## 数据库表（14张，SQLite `data/kline.db`）

| 类别 | 表名 | 说明 |
|------|------|------|
| K线 | `stock_daily`、`trading_calendar` | 日线数据 + 交易日历 |
| 持仓 | `position`、`trade_record`、`position_snapshot` | 头寸 + 交易流水 + 日快照 |
| 关注 | `watchlist`、`watchlist_daily` | 关注票 + 每日指标快照 |
| B1追踪 | `b1_scan`、`b1_candidate`、`b1_tracking` | 扫描批次 + 候选明细 + 状态追踪 |
| 板块 | `focus_sector`、`focus_sector_daily` | 重点板块 + 日快照 |
| 审计/LLM | `audit_log`、`llm_report` | 操作审计 + LLM 生成缓存 |

## 数据源级联链路（对标 JusticePlutus DataFetcherManager）

### K 线日线

```
registry.get_kline / kline_filler.ensure_candles
  → ① iFind (HTTP: date_sequence → cmd_history → snapshot)  [付费, 优先]
  → ② Efinance (免费, 快)                                     [pip efinance]
  → ③ Akshare (免费, 全但慢, 含限速 0.5s)                     [pip akshare]
  → ④ FreeStockLine (免费, K线不准但能用)                     [subprocess CLI]
  → ⑤ Baostock (免费, 需 login/logout)                       [pip baostock]
  → ⑥ SQLite stock_daily (本地缓存, 最终兜底)
```

**熔断规则**：单源连续失败 3 次自动禁用，成功后重置。

### 实时行情

```
① iFind THS_RQ → ② FreeStockLine → ③ Akshare(sina/tencent) → ④ Efinance
```

### 板块/成分股

```
① iFind smart-query → ② FreeStockLine sector → ③ Akshare stock_board
```

### 筹码分布

```
① Akshare (akshare_data/chip.py) → ② SQLite fallback
```

实现位置：
- `scripts/data_source/kline_cascade.py` — `KlineCascade` 类（多源级联管理器）
- `scripts/data_source/fetchers/` — `EfinanceFetcher` / `AkshareFetcher` / `BaostockFetcher`
- `scripts/data_source/registry.py` — `DataSourceRegistry.get_kline` 内部走级联
- `scripts/storage/kline_filler.py` — `ensure_candles` 走级联补缺

## B1 状态机

```
watching → near_b1(J<20) → b1(有信号) → bought(用户买入) → holding
   ↑                         │                │                │
   │                         ↓                │                ↓
   └──(7天观察期满)── observing ←(B1消失)─────┘         sell_candidate → sold
```

## 环境变量

```bash
# 数据源
ZX_IFIND_CLI=/path/to/ifind_cli.py
ZX_FREE_CLI=/path/to/stockline_cli.py
ZX_DATA_SOURCE=auto|ifind|free|cache

# 黑名单
ZX_BAN_BOARDS=688,920,8
ZX_BAN_ST=true|false
ZX_BAN_CODES=000001,000002

# LLM (Phase F, 可选)
ZX_LLM_BASE_URL=https://api.anthropic.com/v1
ZX_LLM_API_KEY=<key>
ZX_LLM_MODEL=claude-sonnet-4-6
ZX_LLM_THINKING=true
ZX_LLM_THINK_BUDGET=4096
```

## 迭代路线

| Phase | 内容 | 状态 |
|-------|------|------|
| 1-3 | 指标计算 + 数据源 + 板块扫描 + 飞书发布 | ✅ 完成 |
| A | SQLite K线库 + ensure_candles + 交易日历 | ✅ 完成 |
| B | 多数据源降级（iFind→free→akshare→SQLite） | 🔄 进行中（akshare_data/ 已建） |
| C | 持仓管理 + 关注列表 + B1追踪 + 日终流程 | ✅ 完成 |
| D | iFind 日快照 (THS_SS) | 🔄 daily_update.py 已实现三层策略 |
| E | 飞书增强（Webhook/定时任务） | 📋 计划中 |
| F | LLM 报告增强（持仓家书/板块叙事/交易诊断） | 🔄 llm/ 框架就绪，待接入 |
| G | 综合看板与复盘 | 📋 设计文档就绪 |

详细计划见 `docs/` 目录。
