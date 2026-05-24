"""
LLM 配置 — OpenAI-compatible 协议，支持 DeepSeek/Kimi/Anthropic
环境变量:
  ZX_LLM_BASE_URL    → API endpoint
  ZX_LLM_API_KEY     → API Key
  ZX_LLM_MODEL       → 模型名
  ZX_LLM_THINKING    → 启用思考模式（true/false，默认 false）
  ZX_LLM_THINK_BUDGET→ 思考 token 预算（默认 4096）
"""
import os
from dataclasses import dataclass


@dataclass
class LLMConfig:
    base_url: str
    api_key: str
    model: str
    available: bool
    thinking: bool = False
    think_budget: int = 4096

    @classmethod
    def from_env(cls) -> "LLMConfig":
        base_url = os.environ.get("ZX_LLM_BASE_URL", "https://api.anthropic.com/v1")
        api_key = os.environ.get("ZX_LLM_API_KEY", "")
        model = os.environ.get("ZX_LLM_MODEL", "claude-sonnet-4-6")
        available = bool(api_key)
        thinking = os.environ.get("ZX_LLM_THINKING", "").lower() in ("true", "1", "yes")
        think_budget = int(os.environ.get("ZX_LLM_THINK_BUDGET", "4096"))
        return cls(base_url=base_url, api_key=api_key, model=model, available=available,
                   thinking=thinking, think_budget=think_budget)

    def __repr__(self):
        return f"LLMConfig(model={self.model}, available={self.available}, thinking={self.thinking})"


_config: LLMConfig | None = None


def get_llm_config() -> LLMConfig:
    global _config
    if _config is None:
        _config = LLMConfig.from_env()
    return _config
