# 知行股票分析系统

基于**知行超级B1、单针下20、知行趋势线、缩爆B1**等自研指标的 A 股量化分析系统。

全流程：数据获取 → 指标计算 → 选股扫描 → 关注分层 → 报告输出。**零外部 git 依赖**，一个文件夹即装即用。

---

## 快速开始

### 1. 环境要求

- **Python 3.10**（掘金 MyQuant SDK 最高支持 3.13，建议 3.10 同时作为子进程解释器）
- **Python 3.14**（主解释器，掘金功能通过 subprocess 调用 3.10）
- **掘金量化终端**（[myquant.cn](https://www.myquant.cn) 下载，免费注册获取 Token）

### 2. 安装依赖

```bash
pip install -r requirements.txt
```

### 3. 配置环境变量

```bash
# === 必配 ===
# 掘金 MyQuant Token（在掘金终端 → 用户 → 密钥管理 获取）
export ZX_MYQUANT_TOKEN="your_myquant_token_here"

# === 可选 ===
# LLM 增强（Anthropic / OpenAI 兼容 API）
export ZX_LLM_API_KEY="sk-xxx"
export ZX_LLM_BASE_URL="https://api.anthropic.com/v1"
export ZX_LLM_MODEL="claude-sonnet-4-6"

# Web Search（Tavily，市场报告用）
export TAVILY_API_KEY="tvly-xxx"

# 飞书发布（可选）
# 需安装: npm install -g feishu-mcp
export FEISHU_APP_ID="your_app_id"
export FEISHU_APP_SECRET="your_secret"
```

### 4. 初始化数据库

```bash
cd scripts
python cli.py data sync --target calendar   # 交易日历（自动完成）
```

首次使用数据库会在 `data/kline.db` 自动创建，包含所有表结构。

### 5. 拉取全市场K线

```bash
# 全市场全量拉取（~6小时，首次用）
python cli.py data sync --market --full

# 每日增量更新（定时任务，只拉缺的天数）
python cli.py data sync --market
```

### 6. 验证

```bash
python cli.py quote --symbol 002693         # 实时行情
python cli.py trend --symbol 300083         # 知行趋势
python cli.py scan --name 创新药 --auto-save # 板块B1扫描
```

---

## 核心能力

| 能力 | 命令 | 说明 |
|------|------|------|
| **实时行情** | `quote --symbol\|--holdings\|--watch\|--index` | 掘金→腾讯→akshare 三级级联 |
| **K线数据管理** | `data sync [--market\|--all]` | 纯拉数据不算指标，定时任务用；支持增量模式断点续扫 |
| **指数数据** | `data sync --target index` | 七大指数日线到 index_daily 表 |
| **交易日历** | `data sync --target calendar` | 五级降级：掘金→新浪→iFind→baostock→日历估算 |
| **选股扫描** | `scan [--name\|--market\|--codes]` | B1+缩量爆发+知行趋势；数据不足自动补；自动分入关注列表 |
| **知行趋势** | `trend --symbol C` | 黄白线独立分析：趋势状态+斜率+穿越+拐点+综合评分 |
| **B1指标** | `indicator --symbol C` | 原始B1/超卖缩量B/回踩白线B/回踩黄线B/超卖超缩量B 等7种信号 |
| **缩爆B1** | `suo-bao --symbol C` | 爆量后缩量回踩支撑模式识别 |
| **持仓管理** | `holdings add\|list\|report` | 持仓CRUD + 交易流水 + 日报/复盘(LLM) |
| **关注列表** | `watch add\|remove\|promote\|demote` | 分层管理：重点(level=1) + 普通(level=2) |
| **日更全流程** | `daily-update` | K线同步→B1→趋势→状态转移→分层入库→报告 |
| **市场环境报告** | `market-report` | 指数+板块B1密度+WebSearch+LLM解读 |
| **个股分析** | `analyze --symbol C [--deep\|--trade]` | 技术解读/深度分析/交易诊断(LLM) |
| **飞书发布** | `publish --input FILE` | MD报告→飞书文档 |

---

## 数据源级联

```
K线获取: 掘金myquant → 腾讯fqkline → baostock → SQLite本地缓存
实时行情: 掘金current() → 腾讯qt.gtimg.cn → akshare spot_em
交易日历: 掘金get_trading_dates → 新浪tool_trade_date → iFind → baostock → 日历估算
指数行情: 掘金history() → 腾讯fqkline
行业分类: baostock query_stock_industry（证监会标准，5200+只×83行业）
```

**无需克隆外部 git 仓库。** 所有数据源都是 pip 包或 HTTP API。

---

## 数据库表

SQLite 单文件 `data/kline.db`，全部 Git 同步：

| 类别 | 表名 | 说明 |
|------|------|------|
| K线 | `stock_daily` | 日线OHLCV（含 source 字段标记数据来源） |
| 指数 | `index_daily` | 七大指数日线 |
| 日历 | `trading_calendar` | 交易日历缓存 |
| 股票元信息 | `stock_info` | 全市场代码+名称 |
| 行业索引 | `sector_index` | code→证监会行业 |
| 板块成分股 | `sector_stock` | 东财概念/行业板块成分股缓存 |
| 持仓 | `position` / `trade_record` / `position_archive` | 头寸+交易流水+已清仓归档 |
| 账户 | `account_snapshot` | 每日账户快照 |
| 关注 | `watchlist` / `watchlist_daily` | 分层关注+每日指标快照 |
| B1 | `b1_scan` / `b1_candidate` / `b1_tracking` | 扫描批次+候选+状态追踪 |
| LLM | `llm_report` | LLM生成缓存 |
| 审计 | `audit_log` | 操作审计日志 |

---

## CLI 命令全景

### 数据层（获取+存储）

```bash
data sync --target kline --market          # 全市场增量K线
data sync --target kline --market --full   # 全市场全量(首次)
data sync --target kline --code 002693     # 单只补缺
data sync --target index                    # 指数K线
data sync --target calendar                 # 交易日历
quote --symbol 002693                       # 个股行情
quote --holdings                            # 持仓行情
quote --index                               # 指数行情
```

### 计算层（扫描+选股）

```bash
scan --name 创新药 --auto-save              # 板块B1扫描
scan --market --auto-save                   # 全市场B1扫描
scan --codes 002693,300083 --auto-save      # 指定列表
trend --symbol 300083                       # 知行趋势分析
indicator --symbol 002693                   # B1指标计算
suo-bao --symbol 300083                     # 缩爆B1扫描
```

### 分析层（LLM+报告）

```bash
analyze --symbol 002693                     # 个股技术解读
analyze --symbol 002693 --deep              # 深度分析(基本面+筹码+产业链)
analyze --symbol 002693 --trade buy --qty N # 交易前诊断
holdings report                             # 持仓日报
holdings report --review                    # 持仓复盘
market-report                               # 市场环境报告
market-report --theme 电气设备               # 主线专题
```

### 管理层（持仓+关注）

```bash
holdings add --code C --cost X --qty N      # 新增持仓
holdings list --verbose                     # 列出持仓
trade add --code C --direction buy --qty N --price P  # 交易流水
watch promote --code C                      # 升级重点
watch demote --code C                       # 降级普通
watch list --level 1                        # 只看重点
account-update --total X --cash Y           # 账户快照
```

### 日更全流程

```bash
daily-update --days 125                     # K线同步→B1→趋势→关注分层→报告
```

---

## 目录结构

```
知行股票分析系统/
├── README.md                    ← 本文件
├── SKILL.md                     ← OpenClaw Skill 定义
├── CLAUDE.md                    ← Claude Code 指导
├── requirements.txt             ← Python 依赖清单
├── setup.py                     ← 安装脚本
├── scripts/
│   ├── cli.py                   ← 统一 CLI 入口(33个子命令)
│   ├── indicators/
│   │   ├── b1_calculator.py     ← 知行超级B1(7种信号)
│   │   ├── trend_analyzer.py    ← 知行趋势(黄白线独立分析)
│   │   └── suo_bao_b1.py        ← 缩爆B1识别
│   ├── data_source/
│   │   ├── kline_coordinator.py ← K线获取协调者(日期/补缺/级联)
│   │   ├── kline_cascade.py     ← 多源级联管理器
│   │   ├── quote_fetcher.py     ← 实时行情三级级联
│   │   ├── trading_calendar.py  ← 交易日历五级降级
│   │   ├── web_search.py        ← Tavily Web Search
│   │   ├── sector_store.py      ← 板块成分股缓存
│   │   ├── proxy_rotator.py     ← 代理轮转引擎
│   │   └── fetchers/            ← 掘金/腾讯/baostock/东财 fetcher
│   ├── storage/
│   │   ├── db.py                ← SQLite 数据库(17张表)
│   │   ├── kline_filler.py      ← K线按需填充
│   │   └── portfolio_db.py      ← 持仓/交易/关注/板块 CRUD
│   ├── tracking/
│   │   ├── daily_review.py      ← 日终追踪
│   │   ├── state_machine.py     ← B1状态机(9状态流转)
│   │   └── trend_tracker.py     ← 趋势状态转移判定
│   ├── scanning/
│   │   └── sector_scanner.py    ← 板块扫描引擎
│   ├── reporting/
│   │   ├── generator.py         ← Markdown报告
│   │   └── feishu_publisher.py  ← 飞书发布
│   ├── llm/
│   │   ├── client.py            ← LLM客户端
│   │   └── enhancer.py          ← LLM增强器
│   └── config/
│       ├── blacklist.py         ← 黑名单(688/920/8/ST)
│       ├── llm_config.py        ← LLM配置
│       └── theme_chains.py      ← 产业链映射+板块映射
├── data/
│   └── kline.db                 ← SQLite 数据库(已入Git)
├── docs/                        ← 文档
├── references/                  ← 指标/能力参考
└── templates/                   ← 报告模板
```

---

## 环境变量速查

| 变量 | 必填 | 说明 |
|------|:--:|------|
| `ZX_MYQUANT_TOKEN` | ✅ | 掘金量化 Token |
| `ZX_MYQUANT_PYTHON` | | 掘金子进程 Python 路径(默认 D:/Development/Python/python.exe) |
| `ZX_LLM_API_KEY` | | LLM API Key |
| `ZX_LLM_BASE_URL` | | LLM API URL |
| `ZX_LLM_MODEL` | | LLM 模型名 |
| `TAVILY_API_KEY` | | Tavily Web Search API Key |
| `ZX_PROXY_LIST` | | 代理列表(辣脚格式: host:port:user:pass) |
| `ZX_PROXY_API_URL` | | 代理API地址 |
| `ZX_PROXY_AUTH` | | 代理固定用户名密码 |
| `ZX_BAN_BOARDS` | | 排除代码前缀(默认 688,920,8) |
| `ZX_BAN_ST` | | 排除ST(默认 true) |
| `FEISHU_APP_ID` | | 飞书应用ID |
| `FEISHU_APP_SECRET` | | 飞书应用密钥 |

---

*知行系统 仅供参考，不构成投资建议。投资有风险，入市需谨慎。*
