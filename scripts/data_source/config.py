"""
数据源配置 — 双环境兼容（OpenClaw / 本地调试）

环境检测:
  - OpenClaw (Linux):  自动使用 ~/.openclaw/workspace/skills/ 下的 CLI 路径
  - 本地 (Windows):    需通过环境变量或配置文件指定 Python 和 CLI 路径

环境变量覆盖（优先级最高）:
  ZX_IFIND_PYTHON    → iFind 的 Python 解释器路径
  ZX_IFIND_CLI       → iFind CLI 脚本路径
  ZX_FREE_PYTHON     → freeStockLine 的 Python 解释器路径
  ZX_FREE_CLI        → freeStockLine CLI 脚本路径
  ZX_DATA_SOURCE     → 强制数据源: ifind | free | auto
"""
import os
import platform
import sys


def _is_openclaw():
    """检测是否在 OpenClaw 平台运行"""
    return platform.system() == "Linux" and os.path.exists(
        os.path.expanduser("~/.openclaw/workspace-stocktrade-agent")
    )


def _resolve_python():
    """解析 Python 解释器路径"""
    if sys.executable and os.path.exists(sys.executable):
        return sys.executable
    return "python3"


class DataSourceConfig:
    def __init__(self):
        self.is_openclaw = _is_openclaw()

        # iFind (同花顺付费源)
        self.ifind_python = os.environ.get(
            "ZX_IFIND_PYTHON",
            "/tmp/ifind_venv/bin/python3" if self.is_openclaw else _resolve_python()
        )
        # 本地路径: workspace 下的 ifind-skill clone
        _local_ifind = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "..", "ifind-skill", "tonghuashun-ifind-skill", "scripts", "ifind_cli.py"
        )
        _oc_ifind = os.path.expanduser(
            "~/.openclaw/workspace/skills/tonghuashun-ifind-skill/scripts/ifind_cli.py"
        )
        self.ifind_cli = os.environ.get(
            "ZX_IFIND_CLI",
            _oc_ifind if self.is_openclaw else os.path.abspath(_local_ifind)
        )

        # freeStockLine (免费源)
        self.free_python = os.environ.get(
            "ZX_FREE_PYTHON",
            os.path.expanduser(
                "~/.openclaw/workspace/skills/freestocklineskill/.venv/bin/python3"
            ) if self.is_openclaw else _resolve_python()
        )
        _local_free = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "..", "freestock-skill", "freestocklineskill", "scripts", "stockline_cli.py"
        )
        _oc_free = os.path.expanduser(
            "~/.openclaw/workspace/skills/freestocklineskill/scripts/stockline_cli.py"
        )
        self.free_cli = os.environ.get(
            "ZX_FREE_CLI",
            _oc_free if self.is_openclaw else os.path.abspath(_local_free)
        )

        # 强制数据源（ifind / free / auto）
        self.force_source = os.environ.get("ZX_DATA_SOURCE", "auto")

        # 此 Python 进程（用于本地计算指标）
        self.local_python = _resolve_python()

        # 工作目录
        self.workspace = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__)
        )))

    def available_sources(self):
        """返回可用的数据源列表"""
        sources = ["local"]  # 本地计算永远可用
        if self.ifind_cli and os.path.exists(self.ifind_cli):
            sources.append("ifind")
        if self.free_cli and os.path.exists(self.free_cli):
            sources.append("free")
        return sources

    def __repr__(self):
        return (
            f"DataSourceConfig(openclaw={self.is_openclaw}, "
            f"available={self.available_sources()}, "
            f"force={self.force_source})"
        )


# 全局单例
config = DataSourceConfig()
