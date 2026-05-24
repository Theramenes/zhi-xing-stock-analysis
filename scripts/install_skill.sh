#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_DIR="${ROOT_DIR}/知行股票分析系统"

echo "=== 知行股票分析系统 Skill 安装 ==="

# 1. 安装依赖
echo ""
echo "[1/3] 安装 Python 依赖..."
pip install -q requests pandas akshare efinance baostock openai 2>&1 | tail -3

# 2. iFind token 检查
echo ""
echo "[2/3] 检查 iFind 配置..."
IFIND_CLI="$HOME/.openclaw/workspace/skills/tonghuashun-ifind-skill/scripts/ifind_cli.py"
if [ -f "$IFIND_CLI" ]; then
    echo "  iFind CLI 已找到"
    # 检查 token
    TOKEN_FILE="$HOME/.openclaw/tonghuashun-ifind-skill/token_state.json"
    if [ -f "$TOKEN_FILE" ] && grep -q "access_token" "$TOKEN_FILE" 2>/dev/null; then
        echo "  iFind token 已配置"
    else
        echo "  ⚠️  iFind token 未配置！"
        echo "  python $IFIND_CLI auth-set-refresh-token --refresh-token <token>"
    fi
else
    echo "  ⚠️  iFind CLI 未找到，OC 上应已预装"
fi

# 3. LLM 配置检查
echo ""
echo "[3/3] 检查 LLM 配置（可选）..."
if [ -n "${ZX_LLM_API_KEY:-}" ]; then
    echo "  LLM 已配置 (model=${ZX_LLM_MODEL:-default})"
else
    echo "  LLM 未配置 (Phase F 可选)"
    echo "  export ZX_LLM_BASE_URL=https://api.deepseek.com/v1"
    echo "  export ZX_LLM_API_KEY=sk-xxx"
    echo "  export ZX_LLM_MODEL=deepseek-v4-pro"
    echo "  export ZX_LLM_THINKING=true"
fi

# 4. 验证
echo ""
echo "=== 安装完成 ==="
echo ""
echo "验证: cd $SOURCE_DIR/scripts && python cli.py data-report --symbol 601689"
echo "环境检查: python $SOURCE_DIR/scripts/setup.py"
