# 知行股票分析系统

Python CLI 项目。核心能力：板块扫描概览 + 知行 B1 指标扫描 + 飞书文档发布。

## 在新电脑上配

复制这个文件夹到目标机器，然后：

### 1. Python 依赖

```bash
pip install requests   # ifind_client 直接 HTTP 调用需要
```

其余都是 Python 标准库（json/subprocess/sqlite3/datetime），不用装。

### 2. 数据源

```bash
# 在同级目录克隆两个数据源
cd 知行股票分析系统/..
git clone https://github.com/Etherstrings/tonghuashun-ifind-skill ifind-skill
git clone https://github.com/Etherstrings/freeStockLIneskill freestock-skill
```

目录结构应如下：
```
股票投资/
├── 知行股票分析系统/    ← 本项目
├── ifind-skill/         ← 同花顺数据源
└── freestock-skill/     ← 免费数据源
```

`scripts/data_source/config.py` 会自动检测这两个路径。

### 3. iFind Token

在新机器上执行一次：

```bash
python ../ifind-skill/tonghuashun-ifind-skill/scripts/ifind_cli.py \
  auth-set-refresh-token --refresh-token <你的refresh_token>
```

Token 会存到 `~/.openclaw/tonghuashun-ifind-skill/token_state.json`，之后自动刷新。

refresh_token 获取：同花顺超秘账户页 → 复制 refresh_token

### 4. 飞书发布（可选）

```bash
# 需要 Node.js
npm install -g feishu-mcp
```

环境变量（.env 或直接设）：
```
FEISHU_APP_ID=cli_a970b849ecff1ccd
FEISHU_APP_SECRET=<你的secret>
FEISHU_AUTH_TYPE=user
```

### 5. 验证

```bash
cd 知行股票分析系统/scripts
python cli.py indicator --symbol 603206 --input ../data/scan_cache/002460.json
```

## 命令速查

```bash
python scripts/cli.py scan-sector-overview --name 电池       # 板块概览 → 默认发飞书
python scripts/cli.py scan-sector-b1 --name 电池             # B1扫描 → 默认发飞书
python scripts/cli.py scan-sector-b1 --name 电池 --no-publish # 仅本地，不发飞书
python scripts/cli.py indicator --symbol 603206              # 单股指标
python scripts/cli.py list-sectors                           # 已知板块列表
```

## 目录结构

```
scripts/
├── cli.py                    CLI 入口
├── indicators/
│   ├── b1_calculator.py      知行B1/趋势/单针下20 四套指标
│   └── suo_bao_b1.py         缩爆B1 识别
├── data_source/
│   ├── ifind_client.py       iFind K线(双源fallback: date_sequence→history)
│   ├── free_client.py        freeStockLine 免费源
│   ├── registry.py           优先级链路
│   └── config.py             双环境检测
├── scanning/
│   ├── sector_scanner.py     板块扫描(SectorOverview + SectorB1Scanner)
│   ├── industry_analyzer.py  细分行业聚合
│   └── cache_manager.py      K线缓存
└── reporting/
    ├── generator.py           Markdown 报告生成
    ├── publish_to_feishu.py   飞书发布脚本
    └── feishu_publisher.py   飞书接口

references/                   参考文档
├── deployment.md             部署配置
├── sector-routing.md         板块路由规则
├── indicator-guide.md        指标手册
├── capability-matrix.md      数据源能力矩阵
└── ifind-vs-freestock-能力边界.md

data/
├── scan_cache/               K线缓存(按日期分片)
└── reports/local_markdown/   报告输出
```
