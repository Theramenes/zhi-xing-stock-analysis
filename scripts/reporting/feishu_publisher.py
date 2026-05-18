"""
飞书发布器 — 委托给 publish_to_feishu.py（完整版 Markdown→Blocks 转换）
"""
from .publish_to_feishu import publish_file as _publish_file


def publish_report(md_path: str, title: str = None, folder_token: str = None) -> str:
    """一键发布：读取本地MD文件 → 创建飞书文档 → 填充内容 → 返回文档URL"""
    doc_id, url = _publish_file(md_path, title=title)
    return url or ""
