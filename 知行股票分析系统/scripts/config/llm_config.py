"""
LLM 配置 — 多 Profile 支持，按任务自动选择模型

Profile 类型:
  analyst:  DeepSeek + thinking — 深度分析 (analyze --deep, market-report, trade-diagnosis)
  router:   千问 — 快速语义路由 (find "低位的")
  reporter: DeepSeek 无thinking — 报告生成 (holdings report, watchlist report)

环境变量:
  ZX_LLM_DEEPSEEK_KEY  → DeepSeek API Key
  ZX_LLM_QWEN_KEY      → 千问 API Key（可选，无则降级用 DeepSeek）
  ZX_LLM_MODEL          → 全局覆盖模型名
"""
import os
from dataclasses import dataclass, field
from typing import Dict


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
