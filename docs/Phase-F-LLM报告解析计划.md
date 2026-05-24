# Phase F: LLM 报告解析计划

## 调研结论

### JusticePlutus 的 LLM 做法

- 用 `litellm` 做多 provider 路由（Gemini/Anthropic/OpenAI）+ key failover
- **结构化 JSON 输出**：系统 prompt 严格限定 Decision Dashboard 格式（core_conclusion / data_perspective / intelligence / battle_plan）
- **数据增强链路**：实时行情 → 筹码分布 → 趋势分析 → 多维度搜索（Bocha/Tavily/Brave）→ iFind 财务包 → LLM
- **完整性校验 + 自动重试**：必填字段缺失时构建补全 prompt 重新调用
- 分析历史持久化到 SQLite，附带 context snapshot

### 知行录 (zhixinglu) 的 LLM 做法

- FastAPI + 流式 HTML，用 OpenAI SDK（可配置 base_url，模型如 claude-4.6-sonnet）
- **模块化分模块 prompt**：10 个模块各自独立调用 LLM（公司在做什么 / 商业模式 / 财务体检 / 估值坐标 / 最新研报 / 市场分歧 / 股价走势 / 交易参考 / 延展问题）
- **"人话原则"**：prompt 明确要求禁用行业黑话、用类比和具体数字、像朋友说话不打鸡血
- **三大产品功能**：
  1. 个股深度分析（10 维度研报）
  2. 巴菲特来信（每日持仓诊断，巴菲特口吻）
  3. 交易诊断（下单前 6 维度系统检查 + 追问对话）
- 数据全部来自 akshare（免费源）

### 当前 zhi-xing-stock 的 LLM 现状

- **零 LLM 集成**：所有报告都是本地 Python 硬算生成的 Markdown
- 有结构化指标 JSON（B1 信号 / 白黄线 / 评分 / 5 维评分 / 量能状态），但没有自然语言解读
- 报告模板里有占位注释 `*关联分析由AI推理完成*`，实际未实现
- Phase F 在 `迭代需求.md` 中只有空标题，无内容

---

## 借鉴策略（适配 CLI 场景）

不需要流式 HTML 生成器（那是 web 产品），也不需要 litellm 多 provider 路由的复杂度。核心是把**现有结构化指标翻译成自然语言解读**，并生成 **4 类 CLI 可用的增强报告**：

| 功能 | 借鉴来源 | 适配方式 |
|------|---------|---------|
| **个股技术解读** | zhixinglu 模块思想 + JusticePlutus JSON 结构化 | 把 `b1_calculator` 输出的 JSON 喂给 LLM，生成"人话版"技术诊断 |
| **板块扫描增强** | JusticePlutus intelligence + battle_plan | 把 `SectorB1Result` 的批量数据喂给 LLM，生成板块叙事分析 |
| **持仓日报** | zhixinglu 巴菲特来信 | 把 `daily_review` / `position_snapshot` 数据喂给 LLM，生成每日持仓信 |
| **交易诊断** | zhixinglu 交易诊断 | 用户输入买卖意图，LLM 从 6 维度检查（价值/仓位/时机/市场/板块/风险） |

## 批注&功能需求
- 不用HTML, LLM的provider我们能不能这样, 用户正在对话的LLM能不能用? 还是说一定要配一个LLM的API, 我倾向于一个协议的, 比如claude的anthro的协议, 用户配置API key. 

- **持仓日报** 不要巴菲特的口吻, 同时, 并给出次日建议
- **关注列表监控** 增加一个部分, 当每天刷新关注列表状态的时候, 把关注列表的变化以及状态, 总结成报告
- P.S. 需要让这个解读, 能够理解B1这个指标的含义

---

## 实施步骤

### F1: LLM 客户端（1h）

- 新建 `scripts/llm/client.py`
  - 封装 OpenAI SDK（`openai` 包或直接用 `requests` post）
  - 环境变量：`ZX_LLM_BASE_URL`, `ZX_LLM_API_KEY`, `ZX_LLM_MODEL`
  - 支持 `chat(messages, json_mode=True)` 返回结构化 dict
  - 支持 `chat_stream`（为后续可能的前端预留）
  - 简易重试：3 次指数退避
- 配置：`scripts/config/llm_config.py`（从环境变量读取，无密钥时 gracefully degrade）

### F2: Prompt 模板系统（1h）

- 新建 `scripts/llm/prompts/` 目录，每类报告一个 py 文件：
  - `stock_analysis.py` — 个股技术解读 prompt（输入：指标 JSON → 输出：技术诊断/操作建议/风险提醒）
  - `sector_narrative.py` — 板块叙事分析 prompt（输入：SectorB1Result dict → 输出：板块情绪/B1 密度解读/跨股模式）
  - `holdings_letter.py` — 持仓日报 prompt（输入：持仓快照 + 今日涨跌 + B1 状态变化 → 输出：巴菲特式每日信）
  - `trade_diagnosis.py` — 交易诊断 prompt（输入：交易意图 + 个股指标 + 持仓状态 → 输出：6 维度检查清单）
- Prompt 原则（抄 zhixinglu）：
  - 禁用行业黑话，用日常语言
  - 基于数据客观陈述，不给确定性买卖建议
  - 引导用户思考而非替用户决策
  - 语气克制真诚，像朋友说话

### F3: 报告增强层（2h）

- 新建 `scripts/llm/enhancer.py`
  - `enhance_stock_report(code, indicators_json) -> str`：在现有 Markdown 报告末尾追加 "## AI 技术解读"
  - `enhance_sector_report(sector_b1_result) -> str`：在板块扫描报告末尾追加 "## AI 板块叙事"
  - `generate_holdings_letter(holdings_data) -> str`：独立生成每日持仓信 Markdown
  - `diagnose_trade(intent, context) -> str`：独立生成交易诊断 Markdown
- 所有 LLM 生成内容自动写入 SQLite 新表 `llm_report`：

```sql
CREATE TABLE llm_report (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT,               -- 股票代码（板块报告为空）
    report_type TEXT,        -- stock / sector / holdings / trade
    query_date TEXT,
    prompt_hash TEXT,        -- 用于缓存/去重判断
    raw_input TEXT,          -- JSON（输入数据的摘要）
    content TEXT,            -- LLM 生成的 Markdown
    model TEXT,
    tokens_in INTEGER,
    tokens_out INTEGER,
    elapsed_sec REAL,
    created_at TEXT
);
```

### F4: CLI 命令接入（1h）

- `cli.py` 新增子命令：
  - `python cli.py llm-stock --symbol 601689`：单股技术解读（先跑 indicator，再调 LLM）
  - `python cli.py llm-sector --name 电池`：板块扫描 + LLM 叙事增强
  - `python cli.py holdings-letter`：生成今日持仓日报
  - `python cli.py trade-diagnosis --symbol 601689 --action buy --shares 100`：交易前诊断
  - `--no-llm` 全局 flag：跳过 LLM 增强，纯本地报告（默认行为）
- LLM 未配置时给出友好提示："LLM 未配置，跳过 AI 解读。设置 ZX_LLM_API_KEY 开启。"

### F5: 飞书集成（0.5h）

- LLM 增强后的报告同样可走现有 `publish` 流程发到飞书
- 持仓日报可配置每日定时生成 → 飞书推送（Phase E 的定时任务自然承接）

---

## 关键文件

| 文件 | 作用 |
|------|------|
| `scripts/llm/client.py` | OpenAI-compatible LLM 封装 |
| `scripts/llm/prompts/stock_analysis.py` | 个股技术解读 prompt |
| `scripts/llm/prompts/sector_narrative.py` | 板块叙事分析 prompt |
| `scripts/llm/prompts/holdings_letter.py` | 持仓日报 prompt |
| `scripts/llm/prompts/trade_diagnosis.py` | 交易诊断 prompt |
| `scripts/llm/enhancer.py` | 报告增强 orchestrator |
| `scripts/config/llm_config.py` | LLM 配置读取 |
| `scripts/cli.py` | 新增 4 个子命令 |

---

## 验证标准

- `python cli.py llm-stock --symbol 601689` 输出包含 "## AI 技术解读" 的 Markdown，内容人话可读
- `python cli.py holdings-letter` 输出巴菲特式持仓日报，包含今日盈亏、B1 变化、操作建议
- 关闭 LLM 配置后所有命令正常降级为纯本地报告，不报错
- SQLite `llm_report` 表有记录，支持历史查询
