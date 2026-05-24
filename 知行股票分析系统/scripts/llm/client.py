"""
LLM 客户端 — Anthropic Claude 协议（OpenAI-compatible）
用法:
    from llm.client import chat
    result = chat(messages, json_mode=True)  # 结构化 JSON 输出
    result = chat(messages)                   # 普通 Markdown 输出
"""
import json
import time
from config.llm_config import get_llm_config

# 尝试 import openai，失败则用 requests fallback
try:
    from openai import OpenAI
    _HAS_OPENAI = True
except ImportError:
    _HAS_OPENAI = False


def _call_openai(messages: list, json_mode: bool = False, max_tokens: int = 4096) -> dict | None:
    """OpenAI SDK 调用"""
    config = get_llm_config()
    client = OpenAI(base_url=config.base_url, api_key=config.api_key)
    kwargs = dict(
        model=config.model,
        messages=messages,
        max_tokens=max_tokens,
        temperature=0.3,
    )
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}
    # 思考模式 (DeepSeek reasoning / Anthropic extended thinking)
    if config.thinking:
        kwargs["extra_body"] = {
            "thinking": {"type": "enabled", "budget_tokens": config.think_budget}
        }
    resp = client.chat.completions.create(**kwargs)
    content = resp.choices[0].message.content
    # DeepSeek 思考内容在 reasoning_content 字段
    reasoning = getattr(resp.choices[0].message, "reasoning_content", None)
    if reasoning:
        content = f"[思考过程]\n{reasoning}\n\n[分析结论]\n{content}"
    return {
        "content": content,
        "model": resp.model,
        "tokens_in": resp.usage.prompt_tokens if resp.usage else 0,
        "tokens_out": resp.usage.completion_tokens if resp.usage else 0,
    }


def _call_requests(messages: list, json_mode: bool = False, max_tokens: int = 4096) -> dict | None:
    """requests 直接 HTTP 调用（OpenAI-compatible 协议）"""
    import requests
    config = get_llm_config()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {config.api_key}",
    }
    body = {
        "model": config.model,
        "messages": [{"role": m["role"], "content": m["content"]} for m in messages],
        "max_tokens": max_tokens,
        "temperature": 0.3,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if config.thinking:
        body["thinking"] = {"type": "enabled", "budget_tokens": config.think_budget}
    resp = requests.post(
        f"{config.base_url.rstrip('/')}/chat/completions",
        headers=headers,
        json=body,
        timeout=180,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"LLM API error {resp.status_code}: {resp.text[:300]}")
    data = resp.json()
    # OpenAI-compatible 格式
    choice = (data.get("choices") or [{}])[0]
    msg = choice.get("message", {})
    content = msg.get("content", "")
    # DeepSeek 思考内容
    reasoning = msg.get("reasoning_content", "")
    if reasoning:
        content = f"[思考过程]\n{reasoning}\n\n[分析结论]\n{content}"
    if json_mode:
        content = _extract_json(content)
    return {
        "content": content,
        "model": data.get("model", config.model),
        "tokens_in": (data.get("usage") or {}).get("prompt_tokens", 0),
        "tokens_out": (data.get("usage") or {}).get("completion_tokens", 0),
    }


def _extract_json(text: str) -> str:
    """从 LLM 响应中提取 JSON（处理 markdown 代码块包裹）"""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()


def chat(messages: list, json_mode: bool = False, max_retries: int = 3, max_tokens: int = 4096) -> dict | None:
    """
    LLM 对话调用，自动选择 SDK 或 requests fallback。
    Returns: {"content": str, "model": str, "tokens_in": int, "tokens_out": int} | None
    """
    config = get_llm_config()
    if not config.available:
        return None

    caller = _call_openai if _HAS_OPENAI else _call_requests

    last_err = None
    for attempt in range(max_retries):
        try:
            return caller(messages, json_mode=json_mode, max_tokens=max_tokens)
        except Exception as e:
            last_err = e
            if attempt < max_retries - 1:
                wait = 2 ** attempt
                time.sleep(wait)
    raise RuntimeError(f"LLM 调用失败（{max_retries}次重试后）: {last_err}")
