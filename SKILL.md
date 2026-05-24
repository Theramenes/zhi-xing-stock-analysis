# 知行股票分析系统

简称「知行系统」，基于知行超级B1、单针下20、知行趋势线等自研指标的 A 股量化分析技能。覆盖全市场扫描、板块深度分析、持仓评估、早盘前瞻。

## 核心能力

| 能力 | 触发关键词 | 说明 |
|------|-----------|------|
| 全市场B1扫描 | 扫一遍、全市场扫描、B1扫描 | 遍历全A股，计算知行指标，输出B1信号排行 |
| 板块深度扫描 | 扫板块、板块B1、XX板块扫描 | 指定板块，取成分股K线，计算指标，排序输出 |
| 持仓评估 | 持仓分析、看看持仓、评估持仓 | 对持仓个股逐一计算指标+评分，含操作预案 |
| 个股分析 | 分析个股、看看XX、XX怎么样 | 单只股票的全套指标+评分+趋势分析 |
| 早盘前瞻 | 早盘、盘前、今天怎么看 | 外围市场+消息面+竞价+持仓前瞻 |
| 缩爆B1扫描 | 缩爆、爆量、缩量爆量 | 识别爆量后缩量回踩模式的标的 |

## 数据源优先级（硬编码，不可违反）

**K线数据：iFind 专属，严禁降级到 freeStockLine**
> 历史教训：2025-05-15 freeStockLine K线数据与真实行情不符，导致晶丰明源代码混用。K线是交易决策基础，不可妥协。

```
类型 = K线/板块成分股:
  ① iFind（唯一源） → token失效时告知用户，禁止自动降级到free
  ② iFind超时/失败 → 使用本地缓存（如有）

类型 = 行情/板块排行/资金流/龙虎榜:
  ① iFind（主）→ ② freeStockLine（降级，需警告）

类型 = 新闻/公告/研报:
  ① freeStockLine（唯一源）

类型 = 指标计算/评分:
  ① LOCAL 本地计算（永不调用外部API）
```

详细能力边界见 [references/ifind-vs-freestock-能力边界.md](references/ifind-vs-freestock-能力边界.md)

## 鉴权门控（核心规则）

- **禁止静默降级**：iFind token 失效时，必须明确告知用户并等待选择
- **降级必须警告**：切换到免费源时，输出："⚠️ iFind查询失败，已切换至免费数据源，数据精度可能下降"
- **用户覆盖关键词**：
  - `优先免费源` / `用免费数据` / `不用ifind` → 跳过iFind认证，直接走免费源
  - `只用ifind` / `付费数据` → 跳过免费源，仅iFind
  - `双源对比` → 双源同时查询，对比展示差异

## 技术指标（本地计算，4套完整指标）

所有指标通过 `scripts/indicators/b1_calculator.py` 计算：

| 指标套件 | 核心信号 | 参考文档 |
|---------|---------|---------|
| 知行趋势(白黄线) | 白线>黄线=多头，白线<黄线=空头 | [indicator-guide.md](references/indicator-guide.md) |
| 知行超级B1(7种) | 超卖缩量B/拐头B/超缩量B/原始B1/回踩白线B/回踩白线超级B/回踩黄线B | 同上 |
| 基础B1(B1B2B3) | 三级递进：发现→验证→确认 | 同上 |
| 单针下20 | 短期K≤20+长期K≥75，双线归零 | 同上 |
| 缩爆B1 | 爆量后缩量回踩支撑模式 | 同上 |

## 评分体系（5维度100分）

| 维度 | 权重 | 说明 |
|------|------|------|
| B1信号质量 | 30% | 基础B1/B2/B3 + 超级B1 + 共振加分 |
| 趋势质量 | 20% | 白vs黄方向、BBI向上、超牛/强趋势判定 |
| 量能状态 | 15% | 超缩量 > 适当缩量 > 缩量 > 放量阳 > 大绿棒 |
| 异动活跃度 | 20% | 洗盘异动/聚宝盆/双叉戟/近期振幅/远期振幅 |
| 风险评分 | 15% | 持股评分(0-5) + 单针下20 + 死叉/破线/转势 |

等级：S级(90-100) / A级(75-89) / B级(60-74) / C级(40-59) / D级(0-39)

一票否决：涨停封死 / ST / 日成交额<1000万 / 重大利空5日内 → 直接淘汰

## 板块扫描工作流

```
阶段1 板块发现 → 行业板块排行 + 资金流向 + 交叉用户关注
阶段2 个股获取 → 成分股K线(120日)，20线程并行，缓存 scan_cache/
阶段3 指标计算 → b1_calculator.py → 完整指标JSON
阶段4 分类排序 → B1信号 / 近B1(J<20) / 趋势持有 / 其他
阶段5 报告生成 → 统一8模块 markdown 模板
```

## 报告模板

统一8模块结构（参考 [templates/](templates/)）：
1. 大盘状态（指数/涨跌比/成交额/情绪）
2. 行业板块B1强度排行
3. B1信号标的（A级及以上）
4. 近B1观察区（J<20）
5. 持仓个股详细分析（含操作预案）
6. 关注板块个股深度
7. 缩爆B1候选
8. 风险提示

## 黑名单配置

首次使用时自动生效。默认排除以下不可交易的板块：
- **科创板**（688开头）：涨跌幅20%，风险结构不同
- **北交所**（920/8开头）：流动性差
- **ST/\*ST**：风险警示股

可通过环境变量自定义：
```bash
ZX_BAN_BOARDS=688,920,8    # 排除的代码前缀（逗号分隔）
ZX_BAN_ST=true              # 是否排除ST（true/false）
ZX_BAN_CODES=000001,000002  # 额外排除的指定代码
```

## CLI 命令

```bash
# 板块扫描
python scripts/cli.py scan-sector-overview --name 电池        # 板块概览（走势/资金/龙头/异动）
python scripts/cli.py scan-sector-b1 --name 电池              # 板块B1扫描（默认自动入库到关注列表）
python scripts/cli.py scan-market [--max-sectors 10]          # 全市场扫描

# 单股指标
python scripts/cli.py indicator --symbol 603206 [--input candles.json]
python scripts/cli.py suo-bao --symbol 603206 [--input candles.json]

# 持仓管理 (Phase C)
python scripts/cli.py holdings-add --code 002460 --cost 45.2 --qty 1000 [--strategy 长线]
python scripts/cli.py holdings-list [--verbose]
python scripts/cli.py transaction-add --code 002460 --direction buy --price 45.2 --qty 500 --reason B1信号
python scripts/cli.py transaction-list [--code 002460] [--days 90]

# 关注列表 (Phase C)
python scripts/cli.py watchlist-add --code 300750 --name 宁德时代 --reason 板块龙头 --priority 1
python scripts/cli.py watchlist-list [--status active|observing|archived]
python scripts/cli.py watchlist-remove --code 300750 --reason 已建仓

# 日终追踪 (Phase C)
python scripts/cli.py daily-review [--sector 电池,锂电池] [--workers 10]
python scripts/cli.py b1-tracking --code 002460 [--limit 30]

# 重点板块 (Phase C)
python scripts/cli.py focus-sector-add --name 电池 --priority 1
python scripts/cli.py focus-sector-list

# 报告发布
python scripts/cli.py report --input result.json --output report.md
python scripts/cli.py publish --input report.md --title "电池B1扫描"
```

## 部署配置

首次加载时自动检测环境并提示配置。详见 [部署文档](references/deployment.md)。

**核心依赖**: iFind token（必须）、飞书 CLI（可选，用于自动发布）
**OC 就绪**: iFind/freeStockLine 已预装，仅需配置 refresh_token

### LLM 增强（可选，Phase F）

```bash
export ZX_LLM_BASE_URL=https://api.anthropic.com/v1
export ZX_LLM_API_KEY=<your-key>
export ZX_LLM_MODEL=claude-sonnet-4-6
export ZX_LLM_THINKING=true              # 可选
export ZX_LLM_THINK_BUDGET=4096          # 可选
```

配置后，持仓评估/个股分析/板块叙事可自动生成自然语言解读。

## 目录结构

```
知行交易分析系统Skill/
├── SKILL.md                  ← 本文件（Skill 安装入口）
├── docs/                     ← 设计文档（架构/Phase计划/测试指南）
├── tests/                    ← pytest 测试套件
├── scripts/
│   └── install_skill.sh      ← Skill 安装脚本
└── 知行股票分析系统/          ← Skill 实际代码
    ├── SKILL.md              ← Skill 能力说明
    ├── CLAUDE.md             ← Claude Code 开发指南
    ├── scripts/
    │   ├── cli.py            ← 统一CLI入口（18个子命令）
    │   ├── pull_sector_klines.py  ← 板块K线批量拉取
    │   ├── config/
    │   │   ├── blacklist.py       ← 黑名单过滤
    │   │   ├── llm_config.py      ← LLM 配置（Phase F）
    │   │   └── theme_chains.py    ← 行业链映射（机器人/低空经济/AI等）
    │   ├── indicators/
    │   │   ├── b1_calculator.py   ← 4套知行指标
    │   │   ├── suo_bao_b1.py      ← 缩爆B1
    │   │   └── valuation.py       ← 估值指标
    │   ├── data_source/
    │   │   ├── ifind_client.py    ← iFind API
    │   │   ├── free_client.py     ← freeStockLine API
    │   │   ├── registry.py        ← 降级链路
    │   │   ├── fundamental_cascade.py ← 基本面级联
    │   │   └── akshare_data/      ← akshare 子模块（chip/financial/market/news/valuation）
    │   ├── scanning/
    │   │   ├── sector_scanner.py  ← SectorOverview + SectorB1Scanner
    │   │   └── industry_analyzer.py ← 细分行业聚合
    │   ├── storage/
    │   │   ├── db.py              ← SQLite（14张表）
    │   │   ├── kline_filler.py    ← K线按需填充
    │   │   ├── portfolio_db.py    ← 业务CRUD（持仓/关注/B1追踪/板块）
    │   │   └── daily_update.py    ← 三层日更新（THS_RQ→snapshot→date_sequence）
    │   ├── tracking/
    │   │   ├── state_machine.py   ← B1状态机（9状态流转）
    │   │   └── daily_review.py    ← 日终流程（拉K线→算指标→状态转换→预警）
    │   ├── reporting/
    │   │   ├── generator.py       ← Markdown 报告生成
    │   │   ├── data_report.py     ← 数据报告
    │   │   ├── feishu_publisher.py ← 飞书文档发布
    │   │   └── generate_feishu_doc.py
    │   └── llm/                   ← LLM 增强（Phase F）
    │       ├── client.py           ← OpenAI-compatible 客户端
    │       ├── enhancer.py         ← 报告自然语言增强（缓存到 llm_report 表）
    │       ├── market_context.py   ← 市场上下文
    │       └── prompts/           ← 6套 Prompt 模板
    ├── references/                ← 参考文档
    ├── agents/                    ← Agent定义
    ├── data/scan_cache/           ← 按日期分片缓存
    └── templates/                 ← 报告模板

## 能力边界

- ✅ 支持：全市场B1扫描、板块深度扫描、持仓评估、个股分析、早盘前瞻、缩爆B1
- ❌ 不支持：Level-2数据、期货/期权、自动交易执行、投资建议
- ⚠️ 所有分析结果仅供参考，不构成投资建议。投资有风险，入市需谨慎。
