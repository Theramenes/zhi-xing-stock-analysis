# 数据源能力矩阵

## 当前数据源

| 源 | 类型 | 认证 | 覆盖范围 |
|----|------|------|---------|
| iFind (同花顺) | 付费 CLI | access_token + refresh_token | 全A股 K线、实时行情、板块、资金流、龙虎榜、财务 |
| freeStockLine | 免费 CLI | 无需认证 | K线、实时行情、新闻、公告、板块（精度低于iFind） |
| agent-stock | 免费 CLI | 无需认证 | 基于QQ/腾讯API的行情+选股，含评分引擎 |
| LOCAL | 本地计算 | N/A | 4套知行指标、综合评分 |

## 命令能力映射

| 数据需求 | iFind 命令 | freeStockLine 命令 | agent-stock 命令 |
|---------|-----------|-------------------|-----------------|
| 日K线(120天) | `quote-history --symbol SYM --days 120 --period daily --adjust qfq` | 同 | `stock kline SYM` |
| 实时行情 | `quote-realtime --symbol SYM` | 同 | `stock quote SYM` |
| 行业板块列表 | `smart-query "A股行业板块涨跌幅排行"` | `sector --kind industry --action rank` | `stock plate SYM` |
| 板块成分股 | `smart-query "XX板块成分股"` | `sector --kind industry --action members --name XX` | — |
| 涨幅排行 | `smart-query "涨幅排行"` | `rank --kind change --limit 50` | `stock rank` |
| 龙虎榜 | `smart-query "龙虎榜"` | `dragon-tiger` | — |
| 资金流向 | `smart-query "资金流向"` | — | — |
| 新闻/公告 | — | `news` / `announcement` | — |
| 大盘指数 | `smart-query "指数行情"` | — | `stock index` |
| 条件选股 | — | — | `stock query "条件"` |

## 指标数据源

所有指标计算均为 **LOCAL ONLY**，不调用外部 API：

| 指标 | 输入 | 输出 | 脚本 |
|------|------|------|------|
| 知行趋势(白黄线) | 120日K线 | 白线/黄线/BBI/MACD | b1_calculator.py |
| 知行超级B1(7种) | 120日K线 | 7种信号布尔值 | b1_calculator.py |
| 基础B1(B1B2B3) | 120日K线 | B1/B2/B3 布尔值 | b1_calculator.py |
| 单针下20 | 120日K线 | 短期K/长期K/单针/双线归零 | b1_calculator.py |
| 缩爆B1 | 40日K线 | 爆量日/缩量日/支撑位/活跃状态 | suo_bao_b1.py |
| 综合评分(5维) | 指标JSON | 0-100分+等级 | scoring.py (Phase 3) |

## 数据源优先级（硬编码规则）

```
查询请求 → 判断类型 → 分配数据源：

K线/行情/板块/资金流/龙虎榜:
  1. iFind（主）→ 检查token有效
  2. token无效 → 提示用户选择：(a)输入refresh_token (b)用免费源
  3. iFind超时/失败 → 降级freeStockLine + 警告用户

新闻/公告/舆情:
  1. freeStockLine（唯一源）

指标/评分:
  1. LOCAL（唯一源，永远不走外部API）
```

## 用户覆盖关键词

- `优先免费源` / `用免费数据` / `不用ifind` → 跳过 iFind，直接免费
- `只用ifind` / `付费数据` → 跳过免费，仅 iFind
- `双源对比` → 双源同时查询并显示差异
