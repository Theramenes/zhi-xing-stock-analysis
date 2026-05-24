"""
知行系统 — 环境检测与初始化
用法: python scripts/setup.py
"""
import os, sys, subprocess, platform

def _cmd(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, shell=True, timeout=30)
    except Exception:
        return None

def _is_oc():
    return platform.system() == "Linux" and os.path.exists(
        os.path.expanduser("~/.openclaw")
    )

def check_python():
    v = sys.version_info
    ok = v >= (3, 11)
    print(f"  Python {v.major}.{v.minor}.{v.micro}  {'OK' if ok else '需要 >= 3.11'}")
    return ok

def check_pip_pkg(name, import_name=None):
    try:
        __import__(import_name or name)
        print(f"  {name} OK")
        return True
    except ImportError:
        print(f"  {name} 缺失 — pip install {name}")
        return False

def check_ifind():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data_source.config import config
    cli = config.ifind_cli
    exists = os.path.exists(cli)
    status = f"路径: {cli}" if exists else f"未找到: {cli}"
    print(f"  iFind CLI  {'OK' if exists else status}")
    if not exists and _is_oc():
        print(f"    OC 上应已预装，检查 ~/.openclaw/workspace/skills/")
    return exists

def check_ifind_token():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from data_source.registry import registry
    try:
        source = registry.get_source("ifind")
        if source and source.is_available():
            print("  iFind token OK")
            return True
    except Exception:
        pass
    print("  iFind token 需配置:")
    print("    python ifind_cli.py auth-set-refresh-token --refresh-token <token>")
    return False

def check_llm():
    from config.llm_config import get_llm_config
    c = get_llm_config()
    if c.available:
        print(f"  LLM OK ({c.model}, thinking={c.thinking})")
        return True
    else:
        print("  LLM 未配置 (Phase F 可选)")
        print("    export ZX_LLM_BASE_URL=https://api.deepseek.com/v1")
        print("    export ZX_LLM_API_KEY=sk-xxx")
        print("    export ZX_LLM_MODEL=deepseek-v4-pro")
        print("    export ZX_LLM_THINKING=true")
        return False

def check_feishu():
    r = _cmd("npx feishu-mcp --version 2>/dev/null || echo no")
    ok = r and "no" not in (r.stdout or "")
    if ok:
        print("  飞书 CLI OK")
    else:
        print("  飞书 CLI 未安装 (可选): npm install -g feishu-mcp")
    return ok

def check_db():
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
    from storage.db import get_db
    db = get_db()
    stocks = db.stock_count
    rows = db.total_rows
    print(f"  SQLite OK ({stocks} 只股票, {rows} 条K线)")
    return True

def main():
    print("=" * 50)
    print("知行股票分析系统 — 环境检测")
    print("=" * 50)

    results = {}

    print("\n[基础]")
    results["python"] = check_python()

    print("\n[依赖]")
    results["requests"] = check_pip_pkg("requests")
    results["pandas"] = check_pip_pkg("pandas")
    results["akshare"] = check_pip_pkg("akshare")
    results["efinance"] = check_pip_pkg("efinance")
    results["baostock"] = check_pip_pkg("baostock")
    results["openai"] = check_pip_pkg("openai")

    print("\n[iFind]")
    results["ifind_cli"] = check_ifind()
    results["ifind_token"] = check_ifind_token()

    print("\n[LLM]")
    results["llm"] = check_llm()

    print("\n[飞书]")
    results["feishu"] = check_feishu()

    print("\n[数据库]")
    results["db"] = check_db()

    # === 一键修复 ===
    missing_pkgs = [k for k in ["requests","pandas","akshare","efinance","baostock","openai"]
                    if not results.get(k)]
    fixable = (not results.get("ifind_token")) or missing_pkgs

    if fixable:
        print("\n" + "=" * 50)
        print("一键修复")
        print("=" * 50)
        if missing_pkgs:
            print(f"  pip install {' '.join(missing_pkgs)}")
        if not results.get("ifind_token"):
            print("  iFind token: 请运行 auth-set-refresh-token")

    all_ok = all(v for v in results.values())
    print(f"\n{'全部通过' if all_ok else '有项目需要配置'}")

if __name__ == "__main__":
    main()
