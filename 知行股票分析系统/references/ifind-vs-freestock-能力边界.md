# iFinD vs freeStockLine 能力边界区分文档

## 概述

本系统同时接入两个数据源，各有明确的能力边界和适用场景。Agent 执行数据查询时须严格遵循优先级规则，不得混用。

---

## 核心原则：iFinD 优先

```
第1步：iFinD（硬性优先）
  → 至少尝试2种不同的iFinD查询格式
  → 确认iFinD真的拿不到才换
第2步：freeStockLine（仅限补充性数据）
  → 只用于 新闻/公告/资金流拆分/龙虎榜/大宗交易
  → ❌ 禁止用freeStockLine拉K线（数据质量不可靠）
第3步：两者都无 → 明确告知用户
```

---

## 能力全表对比

### 1. K线数据

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 日K线 | ✅ 主数据源（smart-query --query "代码 K线"） | ⛔ 禁止使用 |
| 周/月K线 | ✅ 支持 | ⛔ 禁止使用 |
| 分钟K线 | ✅ 支持 | ⛔ 禁止使用 |

### 2. 实时行情

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 个股实时价/涨跌幅/成交量 | ✅ quote-realtime / market-snapshot | ✅ 可用但非首选 |
| 指数实时行情 | ✅ 支持（上证/深证/创业板等） | ✅ 可用但非首选 |
| ETF/LOF实时行情 | ✅ 支持 | ✅ 可用但非首选 |
| 可转债实时行情 | ✅ 支持 | ✅ 可用但非首选 |
| 批量市场快照 | ✅ market-snapshot | ✅ market-snapshot |

### 3. 涨跌排行 & 榜单

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 成交额榜 | ✅ smart-query 成交额排行 | ✅ rank --kind amount |
| 涨幅榜 / 跌幅榜 | ✅ smart-query 涨幅榜 | ✅ rank --kind changepercent |
| 换手率榜 | ✅ smart-query 换手率排行 | ✅ rank --kind turnover |
| 振幅榜 | ✅ smart-query 振幅排行 | ✅ rank --kind amplitude |
| 量比榜 | ✅ smart-query 量比排行 | ✅ rank --kind quantity_relative_ratio |
| 涨停池 / 跌停池 / 炸板池 | ✅ smart-query 涨停 | ✅ limit-pool |
| 强势股池 | ✅ smart-query 强势股 | ✅ limit-pool --kind up |

### 4. 板块相关

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 行业板块排行 | ✅ smart-query | ✅ sector --kind industry --action rank |
| 概念板块排行 | ✅ smart-query | ✅ sector --kind concept --action rank |
| 板块成分股 | ✅ smart-query | ✅ sector --action constituents |
| 个股所属板块 | ✅ smart-query | ✅ sector --action belong |
| 题材/产业链 | ✅ smart-query | ⚠️ Best-effort |

### 5. 基本面 & 财务

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 营收/净利润/毛利率 | ✅ smart-query / fundamental-basic | ✅ fundamental --pack all |
| PE/PB/ROE | ✅ smart-query | ✅ fundamental --pack all |
| 主营业务/个股画像 | ✅ smart-query | ❌ 不覆盖 |
| 复杂财务筛选 | ✅ smart-query 透传iFinD | ❌ 不覆盖 |

### 6. 资金流向

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 全市场主力资金排行 | ✅ smart-query | ✅ money-flow --scope market |
| 个股资金流 | ✅ smart-query | ⚠️ Best-effort |
| 行业/概念资金流 | ✅ smart-query | ⚠️ Best-effort |
| 超大单/大单/中单/小单逐级拆分 | ✅ iFinD | ✅ freeStockLine（补充来源） |

### 7. 公告 & 研报

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 公告摘要/检索 | ✅ smart-query | ✅ announcement 巨潮资讯 |
| 公告PDF链接 | ✅ iFinD | ✅ 巨潮资讯 |
| 研报/评级/目标价 | ✅ smart-query | ✅ news --kind research |
| 新闻快讯 | ⚠️ 有限支持 | ✅ news --kind news |

### 8. 龙虎榜 & 大宗交易 & 两融

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 龙虎榜 | ✅ smart-query | ✅ dragon-tiger |
| 大宗交易 | ✅ smart-query | ✅ block-trade |
| 融资融券 | ✅ smart-query | ✅ margin-trading |

### 9. 股东 & 分红 & 解禁

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 股东/机构持仓 | ✅ smart-query | ⚠️ Best-effort |
| 分红派息/送转 | ✅ smart-query | ⚠️ Best-effort |
| 解禁/停复牌/风险警示 | ✅ smart-query | ❌ 不覆盖 |

### 10. 新股 & 交易日

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 新股申购/中签/发行 | ✅ smart-query | ❌ 不覆盖 |
| 交易日/休市日 | ✅ date-sequence | ❌ 不覆盖 |

### 11. 其他

| 数据类型 | iFinD | freeStockLine |
|----------|-------|---------------|
| 筹码分布 | ❌ 不覆盖 | ⚠️ Best-effort chip |
| 可转债排行/报价 | ✅ smart-query | ✅ bond |
| 北向/沪深股通 | ✅ smart-query | ❌ 不覆盖 |
| 复杂选股/多条件筛选 | ✅ smart-query 透传iFinD | ❌ 不覆盖 |

---

## iFinD 独家负责（🚫禁freeStockLine）

- **日K线数据**：smart-query --query "代码 日K线 30天"
- **实时行情**：个股、指数、板块实时价
- **板块成分股**：板块内个股列表
- **板块涨幅排行**：行业/概念板块当日涨幅
- **题材概念股列表**：某题材下的股票
- **基本面指标**：营收、利润、毛利率、PE/PB等
- **市场快照**：大盘指数走势
- **所有K线相关数据**：日/周/月/分钟K线

## freeStockLine 仅限（降权至最低）

- **新闻/公告/研报摘要**（补充性来源）
- **资金流向逐级拆分**（超大单/大单/中单/小单）
- **龙虎榜、大宗交易、融资融券**
- **筹码分布**
- ❌ **不能用于拉K线**（历史数据经常与真实行情不符）

---

## Agent 决策口诀

```
有 iFinD → 先用 iFinD smart-query
iFinD 无 → 看数据类别
  K线类 → 只能等iFinD修复，不换源
  榜单类 → 可用freeStockLine rank/limit-pool
  资金流 → 可用freeStockLine money-flow
  公告/新闻 → 可用freeStockLine announcement/news
  龙虎榜/大宗/两融 → 可用freeStockLine dragon-tiger/block-trade/margin-trading
两者都无 → 明确告知用户不覆盖
```

---

## 历史教训（禁止再次犯错）

**2025-05-15**: 多次用freeStockLine拉K线导致数据错误
- 晶丰明源代码混用、价格不准
- 后续所有K线查询只走iFinD

**教训**: K线数据是交易决策的基础，数据质量不可妥协。freeStockLine的K线来自公开免费源，未经同花顺专业数据校准，不得用于任何K线场景。
