"""
LLM 配置 — 多 Profile 支持，按任务自动选择模型

Profile 类型:
  analyst:  DeepSeek + thinking — 深度分析 (analyze --deep, market-report, trade-diagnosis)
  router:   千问 — 快速语义路由 (find "低位的")
  reporter: DeepSeek 无thinking — 报告生成 (holdings report, watchlist report)

Key 加载优先级:
  1. 环境变量 ZX_LLM_DEEPSEEK_KEY / ZX_LLM_QWEN_KEY
  2. scripts/.env 文件 (terminal 子进程回退)
  3. 当前目录 .env (进一步回退)
"""
import os
from dataclasses import dataclass, field
from typing import Dict

_ENV_LOADED = False


def _load_dotenv():
    """从 .env 文件加载环境变量（不回退到全局 settings.json）。
    优先级: 环境变量已有 → 跳过; .env 文件 → setdefault.
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    _ENV_LOADED = True

    # 搜索路径: scripts/.env → 项目根/.env
    search_dirs = [
        os.path.dirname(os.path.abspath(__file__)),                    # config/
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),   # scripts/
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),  # 项目根/
    ]
    for d in search_dirs:
        env_file = os.path.join(d, ".env")
        if not os.path.exists(env_file):
            continue
        try:
            with open(env_file, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip().strip('"').strip("'")
                    if key and val and key not in os.environ:
                        os.environ[key] = val
        except Exception:
            pass


@dataclass
class LLMProfile:
    base_url: str
    api_key: str
    model: str
    available: bool
    thinking: bool = False
    think_budget: int = 4096


_DEFAULT_PROFILES: Dict[str, dict] = {
    "analyst": {
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "ZX_LLM_DEEPSEEK_KEY",
        "model": "deepseek-chat",
        "thinking": True,
        "think_budget": 4096,
    },
    "router": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "ZX_LLM_QWEN_KEY",
        "model": "qwen-plus",
        "thinking": False,
        "think_budget": 0,
    },
    "reporter": {
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "ZX_LLM_DEEPSEEK_KEY",
        "model": "deepseek-chat",
        "thinking": False,
        "think_budget": 0,
    },
}


def _build_profile(role: str) -> LLMProfile:
    """根据 role 构建 Profile，不存在则降级到 analyst"""
    _load_dotenv()

    meta = _DEFAULT_PROFILES.get(role)
    if not meta:
        meta = _DEFAULT_PROFILES["analyst"]

    api_key = os.environ.get(meta["key_env"], "")
    if not api_key and role == "router":
        # 千问不可用时降级 DeepSeek
        api_key = os.environ.get("ZX_LLM_DEEPSEEK_KEY", "")
        meta = _DEFAULT_PROFILES["analyst"]

    # 全局模型覆盖
    model_override = os.environ.get("ZX_LLM_MODEL", "")
    model = model_override if model_override else meta["model"]

    return LLMProfile(
        base_url=meta["base_url"],
        api_key=api_key,
        model=model,
        available=bool(api_key),
        thinking=meta["thinking"],
        think_budget=meta["think_budget"],
    )


_profiles: Dict[str, LLMProfile] = {}


def get_profile(role: str = "analyst") -> LLMProfile:
    """获取指定 role 的 LLM Profile。默认 analyst。"""
    global _profiles
    if role not in _profiles:
        _profiles[role] = _build_profile(role)
    return _profiles[role]


def get_llm_config():
    """向后兼容旧接口：返回 analyst profile"""
    return get_profile("analyst")
