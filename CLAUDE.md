# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

知行股票分析系统（简称「知行系统」），基于知行超级B1、单针下20、知行趋势线等自研指标的 A 股量化分析 CLI 工具。覆盖板块概览、板块B1扫描、全市场扫描、持仓评估、早盘前瞻。

## 开发环境

### 依赖

```bash
pip install requests   # iFind HTTP 调用需要
```

其余均为 Python 标准库（json/subprocess/sqlite3/datetime/threading），无需额外安装。

### 外部数据源（必须在同级目录克隆）

```bash
cd 知行交易分析系统/..
git clone https://github.com/Etherstrings/tonghuashun-ifind-skill ifind-skill
git clone https://github.com/Etherstrings/freeStockLIneskill freestock-skill
```

`scripts/data_source/config.py` 会自动检测这两个路径（OC 环境或本地环境）。

### iFind Token 配置（必须）

```bash
python ../ifind-skill/tonghuashun-ifind-skill/scripts/ifind_cli.py \
  auth-set-refresh-token --refresh-token <你的refresh_token>
```

Token 持久化到 `~/.openclaw/tonghuashun-ifind-skill/token_state.json`。

### 飞书发布（可选）

```bash
npm install -g feishu-mcp
```

环境变量：`FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`FEISHU_AUTH_TYPE=user`

## 常用命令

```bash
# 单股指标计算（从 stdin 或 --input 读取 K 线 JSON）
python scripts/cli.py indicator --symbol 603206 --input data/scan_cache/002460.json

# 缩爆B1扫描
python scripts/cli.py suo-bao --symbol 603206 --input candles.json

# 板块概览（走势/资金/龙头/异动，不扫个股）
python scripts/cli.py scan-sector-overview --name 电池

# 板块B1扫描（逐只取K线 + 指标计算）
python scripts/cli.py scan-sector-b1 --name 电池

# 全市场扫描（以板块为单元循环）
python scripts/cli.py scan-market --max-sectors 10

# 从原始JSON生成报告
python scripts/cli.py report --input result.json --output report.md

# 发布报告到飞书
python scripts/cli.py publish --input report.md --title "电池B1扫描"

# 飞书开关（默认 --publish 开启）
python scripts/cli.py scan-sector-b1 --name 电池 --no-publish   # 仅本地
```

## 架构总览

### 数据流架构

```
用户查询 → cli.py 路由 → 数据源层(registry) → 扫描引擎 → 指标计算 → 报告生成 → (飞书发布)
```

### 模块职责

| 模块 | 路径 | 职责 |
|------|------|------|
| CLI 入口 | `scripts/cli.py` | 子命令分发，7个子命令 |
| 指标计算 | `scripts/indicators/` | `b1_calculator.py`（4套指标）、`suo_bao_b1.py`（缩爆模式） |
| 数据源层 | `scripts/data_source/` | 抽象基类 + iFind/Free/Cache 三层降级链路 |
| 扫描引擎 | `scripts/scanning/` | `sector_scanner.py`（SectorOverview + SectorB1Scanner）、`industry_analyzer.py`（细分行业聚合）、`cache_manager.py` |
| 报告生成 | `scripts/reporting/` | `generator.py`（Markdown）、`feishu_publisher.py` + `generate_feishu_doc.py`（飞书） |
| 本地数据库 | `scripts/storage/` | `db.py`（SQLite K线表 `stock_daily`）、`kline_filler.py`（按需补缺） |
| 黑名单 | `scripts/config/blacklist.py` | 688/920/8/ST 过滤，环境变量可覆盖 |

### 数据源优先级（硬编码，不可违反）

**K线/板块成分股：iFind（唯一源）→ 本地缓存** — 严禁降级到 freeStockLine。历史教训：2025-05-15 freeStockLine K线数据与真实行情不符，导致晶丰明源代码混用。iFind token 失效时必须告知用户并等待选择，禁止自动降级。

| 数据类型 | 主源 | 降级 |
|---------|------|------|
| K线/板块成分股 | iFind | 本地缓存 |
| 行情/板块排行/资金流/龙虎榜 | iFind | freeStockLine（降级需输出 ⚠️ 警告） |
| 新闻/公告/研报 | freeStockLine | N/A |
| 指标计算/评分 | LOCAL | N/A |

用户覆盖关键词：`优先免费源` / `用免费数据` → 跳过iFind；`只用ifind` / `付费数据` → 仅iFind；`双源对比` → 双源同时查询。

### 板块查询路由（关键设计）

- **行业优先于概念**：用户同时提行业和概念 → 只走行业。概念 590 只太杂，看不出结构。
- **口语行业名**：iFind 查询用 `"电池行业"`，不用层级路径 `"电力设备-电池"`（前缀匹配会扩大到整个一级行业 408 只）。
- **板块概览 vs B1 扫描拆分为两个命令**：`scan-sector-overview`（不扫个股）和 `scan-sector-b1`（深扫个股K线）。

### 指标计算体系（本地计算，永不调外部API）

4套指标统一通过 `b1_calculator.py` 计算：

| 指标套件 | 核心信号 | 参考文档 |
|---------|---------|---------|
| 知行趋势(白黄线) | 白线>黄线=多头，白线<黄线=空头 | `references/indicator-guide.md` |
| 知行超级B1 | 超卖缩量B/拐头B/超缩量B/原始B1/回踩白线B/回踩白线超级B/回踩黄线B | 同上 |
| 基础B1(B1B2B3) | 三级递进：发现→验证→确认 | 同上 |
| 单针下20 | 短期K≤20 + 长期K≥75，双线归零 | 同上 |
| 缩爆B1 | 爆量后缩量回踩支撑模式 | 同上 |

评分体系：5维度100分（B1信号30% / 趋势质量20% / 量能15% / 异动活跃度20% / 风险15%），一票否决（涨停/ST/成交额<1000万/重大利空5日内）。

### 环境变量

```bash
ZX_IFIND_CLI=/path/to/ifind_cli.py       # iFind CLI 路径覆盖
ZX_FREE_CLI=/path/to/stockline_cli.py    # freeStockLine CLI 路径覆盖
ZX_DATA_SOURCE=auto|ifind|free|cache     # 强制数据源
ZX_BAN_BOARDS=688,920,8                  # 排除代码前缀
ZX_BAN_ST=true|false                     # 是否排除ST
ZX_BAN_CODES=000001,000002               # 排除指定代码
```

## 迭代路线

当前完成 Phase 1-3（指标/数据源/板块扫描），迭代计划见 `迭代需求 - 数据库功能.md`：

- **Phase A**: SQLite K线本地数据库 + `ensure_candles` 按需填充（已部分实现：`scripts/storage/db.py` + `kline_filler.py`）
- **Phase B**: 多数据源降级（iFind → freeStockLine → akshare → 本地缓存）
- **Phase C**: 关注/持仓管理（`data/holdings.yaml` + `data/watchlist.yaml`）
- **Phase D**: iFind 日快照（THS_SS）增量更新
- **Phase E**: 飞书定时任务/Webhook 推送
