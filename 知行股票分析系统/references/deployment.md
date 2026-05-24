# 知行股票分析系统 — 部署配置

## 首次加载时 Skill 自动检测

SKILL.md 加载时，系统会检测当前环境并提示缺失配置。以下为完整配置项说明。

## 环境检测

| 环境 | 系统 | iFind | freeStockLine | Feishu |
|------|------|-------|---------------|--------|
| OpenClaw (Linux) | ✅ | ✅ 已装 | ✅ 已装 | 需装 Node |
| 本地 Windows | ✅ | 需配置 | 需配置 | 需装 Node |
| Claude Code | ✅ | 可选 | 可选 | 可选 |

## 配置项

### 必配

```bash
# iFind（同花顺付费源）—— K线和板块数据的唯一来源
# 获取方式: 同花顺超秘账户页 → 复制 refresh_token
# OC 上: ifind_cli.py 已在 workspace 中，只需配置 token
# 本地: git clone + 配置 token

# 1. 设置 refresh_token（首次，只需一次）
python ifind_cli.py auth-set-refresh-token --refresh-token <你的token>

# 2. 或者直接设 access_token + refresh_token
python ifind_cli.py auth-set-tokens \
  --access-token <access_token> \
  --refresh-token <refresh_token>
```

### 可选

```bash
# 飞书文档发布（不配则跳过飞书发布环节）
# 需要: Node.js + feishu-mcp npm 包
npm install -g feishu-mcp
# 环境变量:
# FEISHU_APP_ID=cli_a970b849ecff1ccd
# FEISHU_APP_SECRET=<secret>
# FEISHU_AUTH_TYPE=user
```

### 黑名单

```bash
# 默认排除: 688(科创板) / 920/8(北交所) / ST
# 自定义:
export ZX_BAN_BOARDS=688,920,8    # 排除的代码前缀
export ZX_BAN_ST=false             # 不排除 ST
export ZX_BAN_CODES=000001         # 排除特定代码
```

### 路径覆盖

```bash
# OC 上自动检测，无需配置。本地可按需覆盖：
export ZX_IFIND_CLI=/path/to/ifind_cli.py     # iFind CLI 路径
export ZX_FREE_CLI=/path/to/stockline_cli.py  # freeStockLine CLI 路径
export ZX_NODE_EXE=/path/to/node              # Node.js 路径
export ZX_DATA_SOURCE=auto                    # auto/ifind/free/cache
```

## OC 上一键启动

OC 上 iFind 和 freeStockLine 已预装在 workspace 中。唯一需要的是 **iFind token**：

```bash
# 在 OC 终端执行一次
python ~/.openclaw/workspace/skills/tonghuashun-ifind-skill/scripts/ifind_cli.py \
  auth-set-refresh-token --refresh-token <你的refresh_token>
```

之后所有知行命令直接可用：
```bash
python cli.py scan-sector-overview --name 电池
python cli.py scan-sector-b1 --name 电池 --publish
```

## 本地 Windows 一键启动

```powershell
# 1. 克隆数据源
git clone https://github.com/Etherstrings/tonghuashun-ifind-skill ../ifind-skill
git clone https://github.com/Etherstrings/freeStockLIneskill ../freestock-skill

# 2. 配置 iFind token
python ../ifind-skill/.../ifind_cli.py auth-set-refresh-token --refresh-token <token>

# 3. 安装飞书 CLI（可选）
npm install -g feishu-mcp

# 4. 运行
python scripts/cli.py scan-sector-overview --name 电池
```

## 初始化检查清单

Skill 加载时会自动检测并提示以下项的状态：

- [ ] iFind CLI 路径存在？ (ifind_cli.py)
- [ ] iFind token 有效？ (auth-set-refresh-token)
- [ ] freeStockLine CLI 路径存在？ (stockline_cli.py) [可选]
- [ ] Node.js 可用？ (发布飞书需要) [可选]
- [ ] feishu-mcp 已安装？ [可选]
- [ ] 黑名单确认？ (默认: 688/920/ST)

## 数据源优先级

```
K线/板块数据 → iFind（唯一源，失败则报错）
新闻/公告    → freeStockLine（唯一源）
指标计算     → LOCAL（永不调外部 API）

⚠️ K线数据绝不降级到 freeStockLine（历史数据不准）
```
