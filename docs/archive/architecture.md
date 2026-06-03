# 知行股票分析系统 — 功能架构

## 总体架构

```
触发层        输入层        数据层            指标层           报告层           输出层
┌────────┐   ┌────────┐   ┌─────────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐
│ CLI    │ → │ 板块名 │ → │ iFind API   │ → │ b1_calc  │ → │ generator│ → │ 飞书文档 │
│ cron   │   │ 股票代码│   │ freeStock   │   │ suo_bao  │   │          │   │ 本地MD   │
│ GitHub │   │ 持仓代码│   │ SQLite DB   │   │          │   │          │   │ JSON摘要 │
│ Actions│   │        │   │             │   │          │   │          │   │          │
└────────┘   └────────┘   └─────────────┘   └──────────┘   └──────────┘   └──────────┘
```

## 各层职责

| 层级 | 模块路径 | 职责 |
|------|---------|------|
| 触发层 | `scripts/cli.py` | 子命令分发：indicator/suo-bao/scan-sector-overview/scan-sector-b1/scan-market/holdings-add/transaction-add/watchlist-add/daily-review/b1-tracking/focus-sector-add/publish |
| 数据层 | `scripts/data_source/` | 抽象基类 + iFind/Free/Cache 三层降级链路 |
| 扫描引擎 | `scripts/scanning/` | `sector_scanner.py`（SectorOverview + SectorB1Scanner）、`industry_analyzer.py`（细分行业聚合） |
| 指标计算 | `scripts/indicators/` | `b1_calculator.py`（4套指标）、`suo_bao_b1.py`（缩爆模式） |
| 本地数据库 | `scripts/storage/` | `db.py`（SQLite：stock_daily/trading_calendar/position/trade_record/watchlist/b1_tracking 等）、`kline_filler.py`（按需补缺）、`portfolio_db.py`（业务CRUD） |
| 日终追踪 | `scripts/tracking/` | `daily_review.py`（拉K线→算指标→状态转换→预警）、`state_machine.py`（watching→near_b1→b1→observing→archived） |
| 报告生成 | `scripts/reporting/` | `generator.py`（Markdown）、`feishu_publisher.py`（飞书文档） |
| 黑名单 | `scripts/config/blacklist.py` | 688/920/8/ST 过滤 |

## 数据源降级链路

```
用户查询K线
  → ① iFind date_sequence（付费，优先）
  → ② iFind cmd_history_quotation（付费，降级）
  → ③ iFind snap_shot 逐日补（付费，单日兜底）
  → ④ freeStockLine（免费，不可靠但能用）
  → ⑤ SQLite stock_daily（离线，最终兜底）
```

**硬编码规则**：K线/板块成分股 **严禁** 自动降级到 freeStockLine，iFind token 失效时必须提示用户。

## 状态机流转

```
                    ┌─────────────────────────────────────┐
                    ↓                                     │
watching ──信号──→ b1 ──信号消失──→ observing ──7天未恢复──→ archived
   │                 │                │
   └─J<20,无信号─→ near_b1          └─J<20──→ near_b1
        │                              │
        └─信号出现──→ b1               └─信号出现──→ b1
```

## 数据库表关系

```
stock_daily (code, date, OHLCV)
  ↑  ensure_candles 按需填充
  ↓  get_candles 查询

watchlist (code, name, status, source, reason, priority, tags)
  ↓  daily_review 每日扫描
watchlist_daily (date, code, J, RSI, 趋势, 白线, 黄线, 评分, signals, B1_active, near_B1)
  ↓  detect_watchlist_changes 跨日对比

b1_tracking (code, date, stage, J, close, signals, trend, score, stage_days)
  ↑  apply_transition 写入

position (code, name, avg_cost, total_qty, strategy)
  ↓  add_transaction 买入/卖出更新
  ↓  snapshot_position 每日快照
trade_record (id, code, direction, qty, price, pnl, balance_qty, avg_cost_after)
```

## 降级矩阵

| 场景 | 主路径 | 降级路径 | 用户感知 |
|------|--------|---------|---------|
| K线获取 | iFind date_sequence | iFind history → snapshot → SQLite | 无感知（自动） |
| iFind token 失效 | iFind | **禁止自动降级**，提示用户选择 | 必须交互 |
| 板块排行 | iFind smart-query | freeStockLine | ⚠️ 警告后降级 |
| 离线环境 | 外部API | SQLite stock_daily | 无数据时提示 |
| 日终追踪 | 实时拉K线 | SQLite 缓存 | 无感知 |
