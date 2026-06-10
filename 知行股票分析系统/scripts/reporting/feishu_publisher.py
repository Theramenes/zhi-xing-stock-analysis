"""
飞书发布器 — 将报告创建为飞书云文档 + Bot 通知
"""
import os
import subprocess
import json
import sys

FEISHU_BOT_USER_ID = "ou_d55b9054133a1e411d6c074e2f6eb11c"

# lark-cli 路径检测
_LARK_CLI = None


def _get_lark_cli() -> str:
    """检测 lark-cli 路径，缓存结果。"""
    global _LARK_CLI
    if _LARK_CLI:
        return _LARK_CLI

    candidates = [
        os.path.expanduser(r"~\AppData\Roaming\npm\lark-cli.cmd"),
        os.path.expanduser(r"~\AppData\Roaming\npm\lark-cli.ps1"),
        "lark-cli",
    ]
    for c in candidates:
        try:
            r = subprocess.run([c, "--version"], capture_output=True, text=True, timeout=5,
                               encoding="utf-8", errors="replace")
            if r.returncode == 0 or "lark" in (r.stdout + r.stderr).lower():
                _LARK_CLI = c
                return c
        except Exception:
            continue
    _LARK_CLI = ""  # not found
    return ""


def save_report(md_content: str, output_path: str) -> str:
    """保存报告到指定路径，返回绝对路径"""
    path = os.path.abspath(output_path)
    with open(path, "w", encoding="utf-8") as f:
        f.write(md_content)
    return path


def _split_large_tables(content: str, max_rows: int = 35) -> str:
    """拆分超大表格为多个小表格，避免飞书 API 行数限制。"""
    import re
    lines = content.split('\n')
    result = []
    table_header = None       # | 代码 | 名称 | ...
    table_sep = None          # |------|------|...
    table_rows = []           # 数据行

    def flush_table():
        nonlocal table_header, table_sep, table_rows
        if not table_header or not table_rows:
            table_header = table_sep = None
            table_rows = []
            return
        # 写入当前批次
        result.append(table_header)
        result.append(table_sep)
        # 分批 30 行
        for chunk_start in range(0, len(table_rows), max_rows):
            chunk = table_rows[chunk_start:chunk_start + max_rows]
            for row in chunk:
                # 转义 cell 内的 |
                cells = row.strip().split('|')
                fixed = '|'.join(c.replace('|', '\\|') for c in cells)
                result.append(fixed)
            if chunk_start + max_rows < len(table_rows):
                # 还没写完，插入新表头
                result.append('')
                result.append(table_header)
                result.append(table_sep)
        result.append('')
        table_header = table_sep = None
        table_rows = []

    in_table = False
    for line in lines:
        stripped = line.strip()
        # 表头行: | col1 | col2 | ...
        if not in_table and re.match(r'^\|[\s\-:|]+\|$', stripped):
            # 这是分隔行，不是表头——但我们已经有了上一行的表头
            pass

        if not in_table and stripped.startswith('|') and stripped.endswith('|'):
            # 可能是表头
            next_is_sep = False
            # 简单判断：下一行是否是分隔行
            table_header = stripped
            in_table = True
            continue

        if in_table and re.match(r'^\|[\s\-:|]+\|$', stripped):
            # 分隔行，确认这是表头
            table_sep = stripped
            continue

        if in_table and stripped.startswith('|') and stripped.endswith('|'):
            # 表格数据行
            table_rows.append(stripped)
            continue

        # 非表格行
        if in_table:
            flush_table()
            in_table = False
        result.append(line)

    # 结尾
    if in_table:
        flush_table()

    return '\n'.join(result)


def _sanitize_lark_md(content: str) -> str:
    """转义 + 拆分大表格，飞书兼容。"""
    return _split_large_tables(content)


def publish_report(md_path: str, title: str = None, folder_token: str = None) -> str:
    """
    将本地 MD 报告发布为飞书云文档。

    1. 转义表格 cell 内的 | → \\| 以兼容飞书解析器
    2. 调 lark-cli docs +create 创建文档
    3. 返回文档 URL，失败返回空字符串
    """
    path = os.path.abspath(md_path)
    if not os.path.exists(path):
        print(f"[Feishu] 文件不存在: {path}", file=sys.stderr)
        return ""

    lark_cli = _get_lark_cli()
    if not lark_cli:
        print("[Feishu] lark-cli 未安装，跳过飞书发布", file=sys.stderr)
        return ""

    title = title or os.path.splitext(os.path.basename(path))[0]

    # 读取原始 MD → 写入临时文件（转义只在报告生成侧做）
    with open(path, 'r', encoding='utf-8') as f:
        raw = f.read()
    # 安全转义：确保表格 cell 内不含裸 |
    sanitized = _sanitize_lark_md(raw)

    file_dir = os.path.dirname(path)
    tmp_name = '_feishu_tmp_.md'
    tmp_path = os.path.join(file_dir, tmp_name)
    with open(tmp_path, 'w', encoding='utf-8') as f:
        f.write(sanitized)

    args = [
        lark_cli, "docs", "+create",
        "--api-version", "v1",
        "--title", title,
        "--markdown", f"@./{tmp_name}",
    ]
    if folder_token:
        args.extend(["--folder-token", folder_token])

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"

    try:
        r = subprocess.run(args, capture_output=True, text=True, timeout=30,
                           encoding="utf-8", errors="replace", env=env,
                           cwd=file_dir)
        os.unlink(tmp_path)
        if r.returncode == 0 and r.stdout.strip():
            url = r.stdout.strip()
            print(f"[Feishu] 文档已创建: {url}")
            return url
        else:
            stderr_info = r.stderr[:500] if r.stderr else ""
            stdout_info = r.stdout[:500] if r.stdout else ""
            print(f"[Feishu] 创建失败 (exit={r.returncode}): {stderr_info} {stdout_info}", file=sys.stderr)
            return ""
    except Exception as e:
        try: os.unlink(tmp_path)
        except: pass
        print(f"[Feishu] 调用异常: {e}", file=sys.stderr)
        return ""


def notify_scan_complete(sector: str, b1_count: int, near_count: int, url: str = "") -> bool:
    """
    发送飞书 Bot 消息通知扫描完成。
    """
    lark_cli = _get_lark_cli()
    if not lark_cli:
        return False

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
