"""
飞书发布器 — 报告保存 + Bot 通知（文档创建由 OC lark-doc skill 接管）
"""
import os
import subprocess

# Bot 通知（可选，仅 OC 环境有效）
FEISHU_BOT_USER_ID = "ou_d55b9054133a1e411d6c074e2f6eb11c"


def save_report(md_content: str, output_path: str) -> str:
    """保存报告到指定路径，返回绝对路径"""
    path = os.path.abspath(output_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_content)
    return path


def publish_report(md_path: str, title: str = None, folder_token: str = None) -> str:
    """
    OC 环境：仅保存报告，文档创建由 lark-doc skill 接管。
    本地 Windows：尝试走 feishu-mcp CLI（如有安装）。
    返回文件路径（OC）或文档 URL（本地）。
    """
    path = os.path.abspath(md_path)
    if not os.path.exists(path):
        return ""
    # OC 上：让 lark-doc 处理
    return f"file://{path}"


def notify_scan_complete(sector: str, b1_count: int, near_count: int, url: str = "") -> bool:
    """
    发送飞书 Bot 消息通知扫描完成（可选，OC 环境有效）。
    """
    import json
    lark_cli = os.path.expanduser(r"~\AppData\Roaming\npm\lark-cli.cmd")
    if not os.path.exists(lark_cli):
        lark_cli = "lark-cli"  # OC Linux PATH
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    content_blocks = [[{"tag": "text", "text": f"知行B1扫描完成: {sector}  B1:{b1_count}  近B1:{near_count}"}]]
    if url:
        content_blocks.append([{"tag": "a", "text": "查看报告", "href": url}])
    content = json.dumps({"zh_cn": {"content": content_blocks}}, ensure_ascii=False)

    try:
        r = subprocess.run(
            [lark_cli, "im", "+messages-send",
             "--user-id", FEISHU_BOT_USER_ID,
             "--msg-type", "post",
             "--content", content,
             "--as", "bot"],
            capture_output=True, text=True, timeout=10,
            encoding="utf-8", errors="replace", env=env
        )
        return '"ok": true' in (r.stdout or "")
    except Exception:
        return False
