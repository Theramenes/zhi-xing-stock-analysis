"""
行业研究收集器 — 读取URL/文本，LLM总结行业逻辑，保存到 references/industry_logic/
"""
import os
import hashlib
from config.llm_config import get_llm_config

REFERENCES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "references", "industry_logic"
)


def fetch_and_summarize(urls: list[str], topic: str) -> str:
    """
    读取多个URL → LLM总结 → 保存为行业逻辑文档。
    返回文件路径。
    """
    import requests

    # 1. 抓取内容
    articles = []
    for url in urls:
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            }
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code == 200:
                # 简单提取文本（去掉HTML标签）
                text = resp.text
                # 保留 5000 字以内
                articles.append({"url": url, "text": text[:5000]})
        except Exception:
            continue

    if not articles:
        return ""

    # 2. LLM 总结
    config = get_llm_config()
    if not config.available:
        return ""

    from llm.client import chat

    combined = "\n\n---\n\n".join(
        f"来源: {a['url']}\n{a['text']}" for a in articles
    )

    messages = [
        {"role": "system", "content": """你是A股行业研究员。请从以下文章中提取{0}行业的投资逻辑。

输出格式（Markdown）：
## {0}行业逻辑

### 一、行业现状
- 当前市场规模、增速、技术阶段

### 二、产业链结构
- 上游/中游/下游，各环节核心A股标的（代码+名称）

### 三、核心驱动
- 需求端驱动力
- 技术变革驱动力
- 政策驱动力

### 四、投资主线
- 主线1: ...
- 主线2: ...

### 五、重点关注标的
| 代码 | 名称 | 环节 | 逻辑 |
|------|------|------|------|

### 六、风险
- 主要风险点""".format(topic)},
        {"role": "user", "content": combined},
    ]

    resp = chat(messages, max_tokens=4096)
    if not resp:
        return ""

    # 3. 保存
    os.makedirs(REFERENCES_DIR, exist_ok=True)
    filename = f"{topic}_行业逻辑.md"
    filepath = os.path.join(REFERENCES_DIR, filename)

    header = f"> 自动生成 | 来源: {', '.join(urls[:3])}\n\n"
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(header + resp["content"])

    return filepath


def get_industry_logic(topic: str) -> str | None:
    """查询已保存的行业逻辑"""
    filepath = os.path.join(REFERENCES_DIR, f"{topic}_行业逻辑.md")
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return f.read()
    return None
