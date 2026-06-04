**ZGNB**

# 知行股票分析系统（zhi-xing-stock）

基于**知行超级B1、单针下20、知行趋势线、缩爆B1**等自研指标的 A 股量化分析系统。

覆盖：数据获取、指数跟踪、全市场 B1 扫描、趋势分析、持仓管理、分层关注、市场环境报告、飞书发布。

**零外部 git 依赖**——一个文件夹即装即用。

---

## 快速开始

### 安装

```bash
cd 知行股票分析系统
pip install -r requirements.txt
```

### 配置

```bash
# 必配：掘金 MyQuant Token（免费注册 myquant.cn 获取）
export ZX_MYQUANT_TOKEN="your_token"

# 可选
export ZX_LLM_API_KEY="sk-xxx"          # LLM 增强
export TAVILY_API_KEY="tvly-xxx"        # Web Search
```

### 启动

```bash
cd scripts
python cli.py data sync --target calendar    # 初始化交易日历
python cli.py data sync --market --full       # 首次全量拉K线（4360只约6小时）
python cli.py scan --market --auto-save       # 全市场 B1 扫描
```

---

## 核心能力

| 能力 | 命令 | 说明 |
|------|------|------|
| **数据获取** | `data sync --market` | K线/指数/日历，增量+断点续扫 |
| **实时行情** | `quote --symbol\|--holdings\|--index` | 掘金→腾讯→akshare |
| **选股扫描** | `scan --name\|--market\|--codes` | B1+趋势+缩爆，自动入关注列表 |
| **知行趋势** | `trend --symbol C` | 黄白线独立分析（5信号+评分） |
| **B1指标** | `indicator --symbol C` | 7种买点信号 |
| **持仓管理** | `holdings add\|list\|report` | 持仓+交易流水+复盘 |
| **分层关注** | `watch promote\|demote` | 重点(1)/普通(2) |
| **日更流程** | `daily-update` | K线→B1→趋势→分层 |
| **市场报告** | `market-report` | 指数+板块+WebSearch+LLM |
| **飞书发布** | `publish` | MD→飞书文档 |

---

## 数据源

**无需克隆外部仓库**。全部通过 pip 包或 HTTP API：

K线：掘金 MyQuant → 腾讯 fqkline → baostock → SQLite
行情：掘金 → 腾讯 qt.gtimg.cn → akshare
日历：掘金 → 新浪 → iFind → baostock → 日历估算

---

## 环境变量

| 变量 | 必填 | 说明 |
|------|:--:|------|
| `ZX_MYQUANT_TOKEN` | ✅ | 掘金量化 Token |
| `ZX_LLM_API_KEY` | | LLM API Key |
| `TAVILY_API_KEY` | | Tavily Web Search |
| `ZX_PROXY_LIST` | | 代理列表 |

---

## 目录结构

```
zhi-xing-stock/
├── README.md                        # 本文件
├── SKILL.md                         # OpenClaw Skill 定义
├── 知行股票分析系统/                  # 实际代码
│   ├── README.md                     # 详细文档
│   ├── requirements.txt              # Python 依赖
│   ├── CLAUDE.md                     # Claude Code 指导
│   ├── scripts/cli.py                # CLI 入口(33个子命令)
│   ├── scripts/indicators/           # B1/趋势/缩爆
│   ├── scripts/data_source/          # 多源级联
│   ├── scripts/storage/              # SQLite(17张表)
│   └── data/kline.db                 # 数据库(已入Git)
├── docs/                             # 项目文档
└── references/                       # 指标/能力参考
```

---

*知行系统 仅供参考，不构成投资建议。投资有风险，入市需谨慎。*
