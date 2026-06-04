# 知行股票分析系统 (zhi-xing-stock)

基于**知行超级B1、单针下20、知行趋势线、缩爆B1**等自研指标的 A 股量化分析技能。

## 核心能力

| 能力 | 命令 | 说明 |
|------|------|------|
| 数据获取 | `data sync [--market\|--all]` | K线/指数/交易日历，增量模式 + 断点续扫 |
| 实时行情 | `quote --symbol\|--holdings\|--index` | 掘金→腾讯→akshare 三级级联 |
| 选股扫描 | `scan [--name\|--market\|--codes]` | B1+缩爆+趋势，自动分流进关注列表 |
| 知行趋势 | `trend --symbol C` | 黄白线独立分析(状态/斜率/穿越/拐点/评分) |
| B1指标 | `indicator --symbol C` | 7种B1买点信号 |
| 持仓管理 | `holdings add\|list\|report` | 持仓CRUD + 复盘/监控 |
| 关注分层 | `watch promote\|demote` | 重点(1)/普通(2) 两级管理 |
| 日更全流程 | `daily-update` | 数据同步→指标→趋势→分层→报告 |
| 市场报告 | `market-report` | 指数+板块B1+WebSearch+LLM |
| 飞书发布 | `publish` | 报告自动发布到飞书文档 |

## 安装配置

### 1. Python 依赖

```bash
pip install -r requirements.txt
```

核心依赖：`akshare` `efinance` `baostock` `gm`(掘金) `tavily-python` `PySocks` `openai` `requests` `pandas`

### 2. 掘金量化终端

1. 下载安装 [掘金量化终端](https://www.myquant.cn)
2. 注册免费账号
3. 终端 → 用户 → 密钥管理 → 获取 Token
4. 设环境变量: `ZX_MYQUANT_TOKEN=你的Token`

**注意**: 掘金 SDK 支持 Python ≤3.13。主环境 3.14 下通过子进程调用 Python 3.10 运行掘金代码。系统会自动检测 `D:/Development/Python/python.exe` 或 `C:/Users/.../Python313/python.exe`。

### 3. 可选配置

```bash
# LLM 增强
ZX_LLM_API_KEY=sk-xxx
ZX_LLM_BASE_URL=https://api.anthropic.com/v1
ZX_LLM_MODEL=claude-sonnet-4-6

# Web Search（Tavily）
TAVILY_API_KEY=tvly-xxx

# 飞书发布 (需 npm install -g feishu-mcp)
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=xxx
```

### 4. 启动

```bash
cd scripts
python cli.py data sync --target calendar   # 初始化交易日历
python cli.py data sync --market --full      # 首次全量拉K线
```

## 数据源

**无需克隆外部 git 仓库。** 所有数据源为 pip 包或 HTTP API：

| 数据源 | 用途 | 类型 |
|--------|------|------|
| 掘金 MyQuant | K线/实时行情/交易日历/股票列表 | pip `gm`（Python 3.10 子进程） |
| 腾讯 fqkline | K线降级 | HTTP 直连 |
| baostock | K线兜底 / 行业分类（证监会标准） | pip `baostock` |
| efinance | 实时行情降级 | pip `efinance` |
| akshare | 实时行情降级 / 板块成分股 / 新闻 | pip `akshare` |
| Tavily | Web Search (市场报告) | pip `tavily-python` |

级联链路：

```
K线: 掘金 → 腾讯 → baostock → SQLite
行情: 掘金 → 腾讯 → akshare
日历: 掘金 → 新浪 → iFind → baostock → 日历估算
```

## 技术指标

| 指标 | 说明 |
|------|------|
| **知行超级B1** | 7种买点：原始B1 / 超卖缩量B / 超卖拐头B / 超卖超缩量B / 回踩白线B / 回踩白线超级B / 回踩黄线B |
| **知行趋势** | 黄白线独立分析：趋势状态 / 斜率 / 穿越(金叉死叉) / 拐点预警 / 综合评分0-10 |
| **基础B1** | B1→B2→B3 三级递进验证 |
| **单针下20** | 超卖针形态识别 |
| **缩爆B1** | 爆量后缩量回踩支撑模式 |

## 数据库

SQLite 单文件 `data/kline.db`（已入 Git），17 张表：

`stock_daily` / `index_daily` / `trading_calendar` / `stock_info` /
`sector_index` / `sector_stock` / `position` / `trade_record` /
`position_archive` / `account_snapshot` / `watchlist` / `watchlist_daily` /
`b1_scan` / `b1_candidate` / `b1_tracking` / `llm_report` / `audit_log`

## 常用操作

```bash
# 每日更新
python cli.py data sync --market              # 只拉缺的K线
python cli.py daily-update --days 125          # 日更全流程

# 选股
python cli.py scan --name 创新药 --auto-save    # 板块B1
python cli.py scan --market --auto-save         # 全市场B1

# 分析
python cli.py trend --symbol 300083             # 趋势
python cli.py analyze --symbol 002693 --deep     # 深度分析

# 报告
python cli.py market-report                     # 市场环境
python cli.py holdings report --review          # 持仓复盘
```

## 黑名单

默认排除：688(科创板) / 920/8(北交所) / ST/*ST
可通过 `ZX_BAN_BOARDS` `ZX_BAN_ST` `ZX_BAN_CODES` 环境变量覆盖。

---

*知行系统 仅供参考，不构成投资建议。*
