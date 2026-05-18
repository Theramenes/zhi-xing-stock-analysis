"""
飞书发布器 — 云文档发布 + Bot 消息通知
"""
import subprocess
from .publish_to_feishu import publish_file as _publish_file


# 飞书 Bot 通知配置
FEISHU_BOT_USER_ID = "ou_d55b9054133a1e411d6c074e2f6eb11c"


def publish_report(md_path: str, title: str = None, folder_token: str = None) -> str:
    """一键发布：读取本地MD文件 → 创建飞书文档 → 填充内容 → 返回文档URL"""
    doc_id, url = _publish_file(md_path, title=title)
    return url or ""


def notify_scan_complete(sector: str, b1_count: int, near_count: int, url: str = "") -> bool:
    """
    发送飞书 Bot 消息通知扫描完成。
    """
    import json as _json, os
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    lark_cli = os.path.expanduser(r"~\AppData\Roaming\npm\lark-cli.cmd")

    # post 富文本：链接用 <tag:a> 显式声明，飞书一定渲染
    content_blocks = [[{"tag": "text", "text": f"知行B1扫描完成: {sector}  B1:{b1_count}  近B1:{near_count}"}]]
    if url:
        content_blocks.append([{"tag": "a", "text": "查看报告", "href": url}])
    content = _json.dumps({"zh_cn": {"content": content_blocks}}, ensure_ascii=False)

    r = subprocess.run(
        [lark_cli, "im", "+messages-send",
         "--user-id", FEISHU_BOT_USER_ID,
         "--msg-type", "post",
         "--content", content,
         "--as", "bot"],
        capture_output=True, text=True, timeout=10,
        encoding="utf-8", errors="replace", env=env
    )
    if r.stderr:
        print(f"  [lark stderr] {r.stderr[:200]}")
    return '"ok": true' in (r.stdout or "")

