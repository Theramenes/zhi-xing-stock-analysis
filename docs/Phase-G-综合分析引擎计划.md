# Phase G: 数据层重建 + 综合分析引擎

## 调研结论

### 两个项目如何把数据喂给 LLM

**核心模式一致**：所有数据源拉取 → 格式化为 Markdown 表格/结构化文本 → 拼成一个完整 prompt → LLM 直接读取并生成分析。不是存成数据库结构让 LLM 读，而是格式化为人类可读的 markdown。

**JusticePlutus 的 prompt 结构**（`_format_prompt()`, analyzer.py:1050-1240）：
```
【实时行情表格】(量比/换手率/PE/PB/市值)
【筹码分布表格】(获利比例/集中度/平均成本/健康度)
【趋势分析表格】(趋势状态/均线排列/乖离率/量能/信号评分)
【iFind 财报摘要】(营收/利润/ROE/毛利率/净利率/资产负债率/现金流)
【iFind 估值摘要】(PE/PB/总市值/流通市值)
【iFind 一致预期】(预测净利润增速)
【iFind 质量判断】(盈利质量/现金流/杠杆/增长)
【舆情情报】(5 维度搜索结果的文本块)
【分析任务指令】(5 个必答问题 + JSON 输出格式)
```

**zhixinglu 的 prompt 结构**（每模块独立调 LLM）：
```
模块1-2: 公司信息 → 业务介绍/商业模式
模块3: 20期财务趋势 + DCF → 财务体检
模块4: 5种估值模型 + PE/PB分位 → 估值坐标
模块5: 研报 + 盈利预测 + 评级分布 → 机构观点
模块6: 新闻 + 研报 + web search → 市场分歧
模块7: 90日K线 + 新闻 → 股价走势
模块9: 全部上下文汇总 + web search → 交易参考
```

### 两个项目的数据源

**JusticePlutus 数据源体系**：

| 数据类别 | 数据源 | 关键方法/文件 |
|---------|--------|-------|
| K线/历史行情 | 5源级联 (HSCloud→Wencai→iFind→Tushare→Akshare) | `DataFetcherManager.get_daily_data()` |
| 实时行情 | 同上5源 | `DataFetcherManager.get_realtime_quote()` |
| 筹码分布 | 同上5源，独立熔断器 | `DataFetcherManager.get_chip_distribution()` |
| 基本面/估值/预测 | iFind API 3路查询 | `IFindService.get_financial_pack()` |
| 新闻/情报 | 6源搜索级联 (Bocha→Tavily→Brave→SerpAPI→MiniMax→SearXNG) | `search_comprehensive_intel()` |
| 趋势分析 | 本地计算 (MA/乖离率/量能) | `TrendAnalyzer.analyze()` |
| 板块排名 | `get_sector_rankings()` | 有数据但**未接入LLM** |
| 市场大局 | `get_main_indices()` / `get_market_stats()` | 有数据但**MarketAnalyzer未实现** |

**zhixinglu 数据源体系**：

| 数据类别 | 数据源 (akshare API) | 关键方法/文件 |
|---------|---------------------|-------|
| K线/历史 | `stock_zh_a_hist` | `market_data.py` |
| 实时行情/个股信息 | 东方财富 `stock_zh_a_spot_em`(主) + 腾讯 `qt.gtimg.cn`(备) + yfinance(HK) | `portfolio_data.py` |
| 财务数据 | `stock_financial_abstract_ths` + sina报表 | `financial_data.py` |
| 估值历史 | `stock_zh_valuation_baidu` (PE/PB全历史) | `valuation_data.py` |
| 新闻/研报/公告 | `stock_news_em` / `stock_research_report_em` / `stock_notice_report` | `news_data.py` |
| 盈利预测 | `stock_profit_forecast_ths` + `stock_profit_forecast_em` | `financial_data.py` |
| 板块排名 | `stock_board_industry_name_em` → 领涨/领跌Top5 | `letter_data.py` |
| 市场大局 | `stock_zh_index_spot_em` (4指数) + `stock_hsgt_north_net_flow_in_em` (北向) | `letter_data.py` |
| 资金流向 | `stock_individual_fund_flow` (主力/超大单) | `letter_data.py` |
| 行业板块K线 | `stock_board_industry_hist_em` (30天) | `diagnosis_data.py` |

### 我们的数据源现状

| 数据类别 | 当前状态 |
|---------|---------|
| K线 | ✅ iFind 4源降级 → SQLite |
| 实时行情 | ✅ iFind snapshot (THS_SS) |
| 板块成分股/排行 | ✅ iFind `a_share_common_query` |
| B1技术指标 | ✅ 本地计算4套指标 |
| 基本面/财务 | ❌ 完全没有 |
| 估值数据 | ❌ 完全没有 |
| 筹码分布 | ❌ 完全没有 |
| 新闻/研报/公告 | ❌ 完全没有 |
| 市场大局/指数 | ❌ 完全没有 |
| 板块排名 | ❌ 没有接入（有iFind但未对接） |
| 资金流向 | ❌ 完全没有 |

### 估值模型对比（zhixinglu 的5种）

| 方法 | 必需数据 | 可靠性 | 说明 |
|------|---------|--------|------|
| **格雷厄姆数** | EPS + BVPS | ★★★ 最稳定 | 盈利正、有净资产的任何公司都适用 |
| **格雷厄姆公式** | EPS + 增长率 | ★★☆ 需要增长假设 | 成长型公司 |
| **反向DCF** | FCF + 总股本 + WACC | ★★★ 最客观 | 告诉"市场在预期什么增速"，不假设 |
| DDM（戈登增长） | 每股股息 + 股息增长率 | ★☆☆ 仅分红股 | 高股息股票 |
| GARP | EPS + 增长率 | ★★☆ PEG思路 | 成长型公司 |

**最可信的两个用于我们的系统**：
1. **格雷厄姆数**：数据需求最少（EPS+BVPS），公式经典，不会给出离谱估值
2. **反向DCF**：不假设增长，而是反推"当前价格隐含的市场预期增速"，让用户自行判断增速是否合理

---

## 实施计划

### G1: akshare 数据层（3h）

从零搭建，不依赖 iFind（逐步脱离 iFind 的第一步）。

新建 `scripts/data_source/akshare_data/` 目录，每类数据一个文件：

**`financial.py`** — 抄 zhixinglu `app/data/financial_data.py`：
- `ak.stock_financial_abstract_ths()` → 财务摘要（营业总收入/净利润/ROE/毛利率/同比增速）
- `ak.stock_financial_report_sina(symbol="现金流量表")` → 经营活动现金流净额、资本支出
- `ak.stock_financial_report_sina(symbol="利润表")` → 完整利润表
- `ak.stock_fhps_detail_ths()` → 历史分红（股息率）

**`valuation.py`** — 抄 zhixinglu `app/data/valuation_data.py`：
- `ak.stock_zh_valuation_baidu(indicator="市盈率")` → PE(TTM) 全历史
- `ak.stock_zh_valuation_baidu(indicator="市净率")` → PB 全历史
- `ak.stock_profit_forecast_ths(indicator="预测年报每股收益")` → 分析师预测 EPS
- `ak.stock_profit_forecast_em()` → 机构评级分布（买入/增持/中性/减持/卖出）

**`news_info.py`** — 抄 zhixinglu `app/data/news_data.py`：
- `ak.stock_news_em()` → 近期新闻（前30条）
- `ak.stock_research_report_em()` → 券商研报（前10篇）
- `ak.stock_notice_report()` → 公司公告（前20条）

**`market.py`** — 抄 zhixinglu `app/data/letter_data.py`：
- `ak.stock_zh_index_spot_em()` → 四大指数（上证/深证/创业板/沪深300）最新价和涨跌幅
- `ak.stock_board_industry_name_em()` → 行业板块涨跌排行 → 领涨Top5 / 领跌Top5
- `ak.stock_hsgt_north_net_flow_in_em(symbol="北上")` → 北向资金净流入
- `ak.stock_individual_fund_flow()` → 个股主力/超大单资金流向

**`chip.py`** — 抄 JusticePlutus 的筹码源：
- `ak.stock_cyq_em()` → 筹码分布（获利比例/平均成本/集中度）
- 后续可扩展 HSCloud/Wencai 源

所有 akshare 调用包装在 `asyncio.to_thread()` 中（为后续 OpenClaw 异步环境铺垫）。

### G2: 估值模型迁移（1h）

从 zhixinglu 抄最可靠的两个，移动到 `scripts/indicators/valuation.py`：

```python
def graham_number(eps, bvps, price) -> dict:
    """格雷厄姆数 = sqrt(22.5 * EPS * BVPS)"""
    
def reverse_dcf(fcf, shares, price, wacc=0.10, terminal_growth=0.025) -> dict:
    """反向DCF：推当前价格隐含的市场预期增速"""
    
def run_valuation_summary(data: dict) -> list[dict]:
    """运行两类估值，返回结果列表"""
```

依赖：`pip install valueinvest`

### G3: 数据报告生成器（2h）— 直接输出，不走 LLM

新建 `scripts/reporting/data_report.py`：

核心思路：所有 raw 数据格式化为 Markdown 表格，**本身就是完整的分析报告**。LLM 只在需要"从数据中推导叙事"时才调用（`--llm` flag）。

```python
def build_individual_report(code, name, context: dict) -> str:
    """个股完整数据报告 → Markdown"""
    # 输出结构化表格，每段都是完整的

def build_sector_b1_report(sector_name, b1_result, market_ctx) -> str:
    """板块 B1 报告 → Markdown（含重点龙头标注 + B1 分布 + 板块定位）"""

def build_market_brief() -> str:
    """市场简报 → Markdown（指数 + 领涨/领跌 + 北向 + 市场宽度）"""
```

输出结构示例（个股报告）：

```
## 个股数据报告: 拓普集团(601689)

### B1 技术指标
| J值 | RSI | 趋势 | 白线 | 黄线 | 评分 | 信号 | 超缩量 | 单针下20 |
|-----|-----|------|------|------|------|------|--------|----------|
| 89  | 81  | 多头 | 63.9 | 63.9 | 4/5  | —    | 否     | 否       |

### 基本面
| 报告期 | 营收(亿) | 净利润(亿) | ROE | 毛利率 | 净利率 | 营收增速 | 利润增速 | 经营现金流(亿) |
|--------|---------|-----------|-----|--------|--------|---------|---------|--------------|

### 估值
| PE(TTM) | PE 5年分位 | PB | PB 5年分位 | 格雷厄姆数 | 反向DCF隐含增速 |
|---------|-----------|-----|-----------|-----------|----------------|

### 筹码
| 获利比例 | 平均成本 | 90%集中度 | 筹码状态 |
|---------|---------|-----------|----------|

### 机构预期
| 评级分布 | 预测EPS | 预测净利润增速 |
|---------|---------|--------------|

### 近期消息
#### 新闻（最近5条）
#### 研报（最近3篇）
#### 公告（关键公告）

### 资金面
| 主力净流入 | 超大单净流入 | 日涨跌幅 |
|-----------|------------|---------|
```

板块报告输出结构（重点——这是我们特色的板块扫描增强）：

```
## 板块扫描: 电池行业

### 市场大局
| 上证 | 深证 | 创业板 | 沪深300 | 北向资金 | 市场宽度 |
|------|------|--------|---------|---------|---------|

### 板块概况
| 板块排名 | 涨跌 | 资金流向 | 成分股数 | B1密度 | 近B1数 |
|---------|------|---------|---------|--------|--------|

### 重点标的（龙头+B1+领涨，三列合并视图）
| 名称代码 | 主营业务 | 板块地位 | 涨跌 | B1状态 | J值 | 评分 | 信号 | 估值分位 | 基本面评级 |
|----------|---------|---------|------|--------|-----|------|------|---------|-----------|
| 宁德时代  | 动力电池 | 🐉龙头/绩优 | +2.1% | — | 55 | 3 | — | PE 35%/PB 50% | ROE 15% 稳健 |
| 赣锋锂业  | 锂盐龙头 | 权重/领涨 | +5.3% | — | 42 | 2 | — | PE 20%/PB 40% | 利润下滑 |
| 天齐锂业  | 锂矿    | 领涨/B1  | +3.8% | ★B1 | 11 | 4 | 拐头B+超缩量 | PE 10%/PB 15% | 周期性低估 |

### B1 候选池
| 排名 | 股票 | B1信号 | 板块地位 | 估值分位 | 基本面 | 主线贴合理由 |
|------|------|--------|---------|---------|--------|-------------|

### 板块阶段判断
（这个段落由 LLM 生成，`--llm` 开启）
→ 从 B1 密度、龙头 vs 二线分布、资金流向中推导板块叙事
→ 示例："电池板块 8/45 B1 多为上游锂矿，龙头宁德未 B1。推测不是板块级恐慌，而是锂盐价格下行导致上游超跌。关注锂盐价格企稳信号。"
```

### G4: LLM 叙事层（1h）— 可选，读 raw 数据推结论

新建 `scripts/llm/prompts/deep_narrative.py`：

**LLM 只做一件事：从 raw 表格数据中推导叙事和模式。**

Prompt 核心：
```
以下是{name}的完整数据报告（已包含B1指标/基本面/估值/筹码/板块/市场数据）。

请从这些数据中推导：
1. 个股矛盾：数据之间的矛盾或相互印证？(例：B1底部信号 vs 估值仍高，说明什么？)
2. 板块定位：该股在板块中的实际角色？（不是从名字猜，而是从财务+涨跌+资金流数据推断）
3. 关键条件：什么条件出现会改变当前判断？
4. 风险注意：数据中的异常需要警惕什么？

不要重复表格里已经有的数字。用数据的逻辑链推导结论。
```

板块报告同样（`--llm` 时）：
```
以下是{板块}的B1扫描数据报告。

请推导：
1. 板块叙事：B1密度/分布/龙头状态意味着什么？(集体超卖/轮动结束/选择性机会？)
2. 横向对比：板块内B1标段 vs 领涨标段的差异说明了什么？
3. 主线贴合：在当下市场环境（领涨板块/资金流向数据已给出），该板块处于什么阶段？
```

**输出格式**：Markdown 段落，追加在数据报告末尾的"## LLM 解读"节中。

#### G5: 信息搜索接入（1h）

新建 `scripts/data_source/search.py`：

```python
def search_stock_news(code: str, name: str) -> list[dict]:
    """搜索个股相关新闻"""
    
def search_sector_news(sector: str) -> list[dict]:
    """搜索板块相关动态"""
```

数据源优先级：
1. akshare `stock_news_em()` — 免费，直接取
2. Web search — 预留接口，OpenClaw 环境启用
3. 降级 → 标注"消息面数据缺失"

#### G6: CLI 接入（1h）

- `python cli.py data-report --symbol 601689` → 纯数据报告（不走 LLM）
- `python cli.py data-report --symbol 601689 --sector 汽车零部件 --llm` → 数据报告 + LLM 叙事
- `python cli.py sector-report --name 电池` → 板块完整报告
- `python cli.py sector-report --name 电池 --llm` → 板块报告 + LLM 板块叙事解读
- `python cli.py market-brief` → 纯数据市场简报

---

## 关键文件

| 文件 | 作用 | 抄谁 |
|------|------|------|
| `scripts/data_source/akshare_data/__init__.py` | 数据层入口 | — |
| `scripts/data_source/akshare_data/financial.py` | 财务数据 | zhixinglu `financial_data.py` |
| `scripts/data_source/akshare_data/valuation.py` | PE/PB历史 + 分析师预期 | zhixinglu `valuation_data.py` |
| `scripts/data_source/akshare_data/news_info.py` | 新闻/研报/公告 | zhixinglu `news_data.py` |
| `scripts/data_source/akshare_data/market.py` | 指数/板块排名/资金流 | zhixinglu `letter_data.py` |
| `scripts/data_source/akshare_data/chip.py` | 筹码分布 | JusticePlutus 筹码源 |
| `scripts/indicators/valuation.py` | 格雷厄姆数 + 反向DCF | zhixinglu `valuation_models.py` |
| `scripts/llm/context_builder.py` | 聚合所有数据 → 格式化prompt | — |
| `scripts/llm/prompts/deep_analysis.py` | 8维深度分析prompt | JusticePlutus + zhixinglu |
| `scripts/llm/prompts/b1_candidate_summary.py` | B1候选池总结prompt | — |
| `scripts/llm/search.py` | Web search接口（预留） | — |

---

## 验证标准

- `pip install akshare valueinvest` 成功
- `python -c "from data_source.akshare_data.financial import get_financial_summary; print(get_financial_summary('601689'))"` 返回真实数据
- `python cli.py deep-analysis --symbol 601689 --sector 汽车零部件` 输出含：基本面/估值/筹码/板块定位/市场大局/B1信号评估
- `python cli.py b1-summary --sector 电池` 输出B1候选池总结，含主线贴合度排序
- 无 akshare 时不崩溃，优雅降级（标注"数据缺失"）
