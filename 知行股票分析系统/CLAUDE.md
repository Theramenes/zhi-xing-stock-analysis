# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

知行股票分析系统（简称「知行系统」），基于知行超级B1、单针下20、知行趋势线等自研指标的 A 股量化分析 CLI 工具。覆盖数据获取、全市场扫描、板块B1分析、持仓管理、关注追踪、趋势分析、市场环境报告。

## 开发环境

### 依赖

```bash
pip install -r requirements.txt
```

核心：`akshare` `efinance` `baostock` `gm`(掘金) `tavily-python` `PySocks` `openai` `requests` `pandas`

### 掘金 MyQuant

掘金 SDK（`gm`）仅支持 Python ≤3.13。主环境 Python 3.14 下，所有掘金调用通过 **subprocess 调用 Python 3.10** 执行。默认路径: `D:/Development/Python/python.exe`

环境变量: `ZX_MYQUANT_TOKEN`

### 数据源级联

**零外部 git 依赖**，全部通过 pip 包或 HTTP API：

```
K线获取: 掘金 → 腾讯fqkline → baostock → SQLite
实时行情: 掘金 → 腾讯qt → akshare
交易日历: 掘金 → akshare新浪 → iFind → baostock → 日历估算
行业分类: baostock(证监会标准, 5200+只×83行业)
```

## 数据管道核心规则

1. **交易日历先行**: `ensure_trading_calendar()` 是所有数据操作的统一前置步骤
2. **日期计算集中**: `KlineFetchCoordinator.compute_start_date()` 是唯一一处交易日反推
3. **增量优先**: `data sync --market` 只拉 `MAX(date) < today` 的票
4. **断点续扫**: 中断后重跑自动跳过已完成的数据
5. **补缺控制在3天内**: `_iterative_backfill` 差<3天跳过(停牌)

## CLI 命令速查

```bash
# 数据
python scripts/cli.py data sync --market --full
python scripts/cli.py data sync --target index
python scripts/cli.py quote --symbol 002693

# 选股
python scripts/cli.py scan --market --auto-save
python scripts/cli.py scan --name 创新药 --auto-save

# 指标
python scripts/cli.py trend --symbol 300083
python scripts/cli.py indicator --symbol 002693
python scripts/cli.py suo-bao --symbol 300083

# 日更
python scripts/cli.py daily-update --days 125

# 报告
python scripts/cli.py market-report
python scripts/cli.py holdings report --review
python scripts/cli.py analyze --symbol 002693 --deep
```

## 环境变量速查

| 变量 | 必填 | 说明 |
|------|:--:|------|
| `ZX_MYQUANT_TOKEN` | ✅ | 掘金 Token |
| `ZX_LLM_API_KEY` | | LLM |
| `TAVILY_API_KEY` | | Web Search |
| `ZX_PROXY_LIST` | | 代理 |
| `ZX_BAN_BOARDS` | | 黑名单 |

## 数据库

SQLite `data/kline.db`（已入 Git），17 张表。关键表：
- `stock_daily`: K线(source字段标记来源)
- `index_daily`: 指数日线
- `sector_index`: code→行业
- `watchlist`: 分层关注(level=1重点/2普通)
- `b1_candidate`: B1候选明细

## B1 状态机

```
watching → near_b1(J<20) → b1(有信号) → bought(用户买入) → holding
   ↑                         │                │                │
   └──(7天观察期满)── observing ←(B1消失)─────┘         sell_candidate → sold
```
