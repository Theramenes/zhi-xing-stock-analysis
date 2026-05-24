# 知行股票分析系统（zhi-xing-stock）

<div align="center">

基于 **知行超级B1、单针下20、知行趋势线** 等自研指标的 A 股量化分析 CLI 工具。

覆盖：板块概览、板块B1扫描、全市场扫描、持仓评估、日终追踪、缩爆B1识别。

</div>

---

## 快速开始

### 1. 安装依赖

```bash
pip install requests
```

其余均为 Python 标准库，无需额外安装。

### 2. 配置外部数据源（必须）

```bash
# 在 zhi-xing-stock 同级目录克隆
git clone https://github.com/Etherstrings/tonghuashun-ifind-skill ifind-skill
git clone https://github.com/Etherstrings/freeStockLIneskill freestock-skill

# 配置 iFind token
python ifind-skill/tonghuashun-ifind-skill/scripts/ifind_cli.py \
  auth-set-refresh-token --refresh-token <你的refresh_token>
```

### 3. 验证安装

```bash
cd 知行股票分析系统/scripts

# 单股指标计算
python cli.py indicator --symbol 603206

# 板块B1扫描
python cli.py scan-sector-b1 --name 电池

# 日终追踪
python cli.py daily-review
```

---

## 目录结构

```
zhi-xing-stock/
├── README.md                   # 本文件
├── SKILL.md                    # OpenClaw Skill 定义
├── scripts/
│   └── install_skill.sh        # Skill 安装脚本
├── tests/                      # 标准测试用例
├── docs/                       # 项目文档
│   ├── 架构计划.md
│   ├── 迭代需求.md
│   └── 关注持仓操作手册.md
└── 知行股票分析系统/            # 实际代码
    ├── scripts/
    │   ├── cli.py              # CLI 入口
    │   ├── indicators/         # 指标计算
    │   ├── data_source/        # 数据源层
    │   ├── scanning/           # 扫描引擎
    │   ├── reporting/          # 报告生成
    │   ├── storage/            # SQLite 数据库
    │   ├── tracking/           # 日终追踪
    │   └── config/             # 黑名单配置
    ├── data/                   # 数据库 + 报告输出
    ├── references/             # 指标说明、能力矩阵
    ├── templates/              # 报告模板
    └── agents/                 # Agent 定义
```

---

## 核心能力

| 能力 | 触发命令 | 说明 |
|------|---------|------|
| 板块概览 | `scan-sector-overview --name 电池` | 走势/资金/龙头/异动，不扫个股 |
| 板块B1扫描 | `scan-sector-b1 --name 电池` | 逐只K线 + 知行指标 + 飞书发布 |
| 全市场扫描 | `scan-market --max-sectors 10` | 按板块循环扫描 |
| 持仓管理 | `holdings-add` / `transaction-add` | 成本/盈亏/交易流水 |
| 关注列表 | `watchlist-add` / `watchlist-list` | 手动 + 自动入库 |
| 日终追踪 | `daily-review` | 关注票 + 持仓票指标更新 + 预警 |
| 缩爆B1 | `suo-bao --symbol 603206` | 爆量后缩量回踩模式识别 |

---

## 架构

```
用户查询 → cli.py → 数据源层(registry) → 扫描引擎 → 指标计算 → 报告生成 → (飞书发布)
```

数据源优先级（硬编码）：
- K线/板块成分股：**iFind 唯一** → SQLite 本地缓存
- 行情/排行/资金流：iFind → freeStockLine（降级需 ⚠️ 警告）
- 新闻/公告：freeStockLine
- 指标计算：**LOCAL 本地，永不调外部API**

详见 `docs/架构计划.md` 和 `知行股票分析系统/references/capability-matrix.md`。

---

## 环境变量

```bash
ZX_IFIND_CLI=/path/to/ifind_cli.py       # iFind CLI 路径覆盖
ZX_FREE_CLI=/path/to/stockline_cli.py    # freeStockLine CLI 路径覆盖
ZX_BAN_BOARDS=688,920,8                  # 排除代码前缀
ZX_BAN_ST=true                           # 是否排除ST
FEISHU_APP_ID=xxx                        # 飞书发布（可选）
FEISHU_APP_SECRET=xxx
```

---

## 测试

```bash
cd 知行股票分析系统
pytest tests/ -v
```

详见 `docs/测试指南.md`。

---

## 迭代计划

- **Phase A**: SQLite K线本地数据库 + `ensure_candles` 按需填充 ✅
- **Phase B**: 多数据源降级（akshare/efinance 兜底）
- **Phase C**: 关注/持仓管理 + 日终追踪 ✅
- **Phase D**: iFind 日快照（THS_SS）增量更新 ✅
- **Phase E**: 飞书定时任务/Webhook 推送

详见 `docs/迭代需求.md`。

---

*知行系统 仅供参考，不构成投资建议。投资有风险，入市需谨慎。*
