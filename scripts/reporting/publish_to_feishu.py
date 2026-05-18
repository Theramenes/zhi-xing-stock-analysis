"""
飞书文档发布 — 完整 Markdown → Feishu Blocks 转换
用法:
  python publish_to_feishu.py report.md                          # 新建文档
  python publish_to_feishu.py report.md --title "标题"            # 指定标题
  python publish_to_feishu.py report.md --doc-id Sl99d0u9Mo...   # 更新已有文档
"""
import subprocess, json, re, os, sys, time, argparse

# === 配置 ===
NODE_EXE = os.environ.get("ZX_NODE_EXE", r"I:\Development\node.js\node.exe")
CLI_JS = os.environ.get(
    "ZX_FEISHU_CLI_JS",
    os.path.expanduser(r"~\AppData\Roaming\npm\node_modules\feishu-mcp\dist\cli\index.js")
)

ENV = os.environ.copy()
ENV.setdefault("FEISHU_APP_ID", "cli_a970b849ecff1ccd")
ENV.setdefault("FEISHU_APP_SECRET", "damkY7ofBkNob9wMm0wTObHvcGUnNpMt")
ENV.setdefault("FEISHU_SCOPE_VALIDATION", "false")
ENV.setdefault("FEISHU_AUTH_TYPE", "user")


def call_feishu(tool_name, params, timeout=30):
    """调用 feishu-tool CLI"""
    json_str = json.dumps(params, ensure_ascii=False)
    # bytes 模式避免 GBK 编码问题
    cmd = [NODE_EXE, CLI_JS, tool_name, json_str]
    result = subprocess.run(cmd, capture_output=True, timeout=timeout, env=ENV)
    stdout = result.stdout.decode('utf-8', errors='replace').strip()
    try:
        return json.loads(stdout) if stdout else {}
    except json.JSONDecodeError:
        return {"raw": stdout[:300] if stdout else "empty"}


def parse_text_styles(text):
    """解析 **bold** 和 `code` 为飞书 textStyles"""
    if not text:
        return [{"text": ""}]
    styles = []
    remaining = text
    while remaining:
        bold_match = re.search(r'\*\*(.+?)\*\*', remaining)
        code_match = re.search(r'`([^`]+?)`', remaining)

        first_pos = float('inf'); first_type = None; first_match = None
        if bold_match and bold_match.start() < first_pos:
            first_pos = bold_match.start(); first_type = 'bold'; first_match = bold_match
        if code_match and code_match.start() < first_pos:
            first_pos = code_match.start(); first_type = 'code'; first_match = code_match

        if first_type is None:
            if remaining:
                styles.append({"text": remaining})
            break
        if first_pos > 0:
            styles.append({"text": remaining[:first_pos]})
        if first_type == 'bold':
            styles.append({"text": first_match.group(1), "style": {"bold": True}})
        elif first_type == 'code':
            styles.append({"text": first_match.group(1), "style": {"inline_code": True}})
        remaining = remaining[first_pos + len(first_match.group(0)):]

    return styles if styles else [{"text": text}]


def parse_table(text):
    """解析 markdown 表格 → (headers, rows)"""
    lines = [l.strip() for l in text.strip().split('\n') if l.strip() and l.strip().startswith('|')]
    if len(lines) < 2:
        return None, None
    headers = [c.strip() for c in lines[0].split('|') if c.strip()]

    data_start = 1
    if lines[1].replace('-', '').replace(':', '').replace('|', '').replace(' ', '') == '':
        data_start = 2

    rows = []
    for line in lines[data_start:]:
        cells = [c.strip() for c in line.split('|') if c.strip()]
        while len(cells) < len(headers):
            cells.append('')
        rows.append(cells[:len(headers)])
    return headers, rows


def create_table(doc_id, index, headers, rows, max_rows_per_call=15):
    """通过 create_feishu_table 创建表格。大表自动拆分。返回创建的块数。"""
    col_size = len(headers)
    chunk_count = (len(rows) + max_rows_per_call - 1) // max_rows_per_call
    if chunk_count > 1:
        print(f"    大表{len(rows)}行→{chunk_count}块")

    created = 0
    for ci in range(chunk_count):
        start = ci * max_rows_per_call
        end = min(start + max_rows_per_call, len(rows))
        chunk_rows = rows[start:end]
        if _create_table_chunk(doc_id, index + ci, headers, chunk_rows):
            created += 1
        else:
            return 0  # 有一块失败则全部放弃
        time.sleep(0.2)
    return created


def _create_table_chunk(doc_id, index, headers, rows):
    """创建单个表格块"""
    col_size = len(headers)
    cells = []

    # 表头
    for col, h in enumerate(headers):
        cells.append({
            "coordinate": {"row": 0, "column": col},
            "content": {
                "blockType": "text",
                "options": {"text": {"textStyles": parse_text_styles(h)}}
            }
        })

    # 数据行
    for ri, row in enumerate(rows):
        for ci, cell in enumerate(row):
            if ci >= col_size: break
            cells.append({
                "coordinate": {"row": ri + 1, "column": ci},
                "content": {
                    "blockType": "text",
                    "options": {"text": {"textStyles": parse_text_styles(str(cell))}}
                }
            })

    params = {
        "documentId": doc_id, "parentBlockId": doc_id,
        "index": index,
        "tableConfig": {
            "columnSize": col_size,
            "rowSize": len(rows) + 1,
            "cells": cells
        }
    }
    result = call_feishu("create_feishu_table", params, timeout=30)
    if 'error' in result:
        print(f"  TABLE ERROR idx={index}: {str(result['error'])[:100]}")
        return False
    return True


def create_blocks(doc_id, index, blocks):
    """批量创建文本块"""
    params = {
        "documentId": doc_id, "parentBlockId": doc_id,
        "index": index, "blocks": blocks
    }
    result = call_feishu("batch_create_feishu_blocks", params, timeout=30)
    if 'error' in result:
        print(f"  BLOCK ERROR at index {index}: {str(result['error'])[:100]}")
        return False
    return True


def clear_document(doc_id):
    """清空文档所有内容"""
    result = call_feishu("get_feishu_document_blocks", {"documentId": doc_id})
    if not isinstance(result, list) or not result:
        return
    children = result[0].get('children', [])
    count = len(children)
    if count == 0:
        return
    print(f"  清空 {count} 个旧块...")
    call_feishu("delete_feishu_document_blocks", {
        "documentId": doc_id, "parentBlockId": doc_id,
        "startIndex": 0, "endIndex": count
    }, timeout=30)
    time.sleep(0.5)


def create_document(title):
    """创建飞书文档，返回 doc_id"""
    root = call_feishu("get_feishu_root_folder_info", {})
    folder_token = ""
    if root.get("root_folder", {}).get("token"):
        folder_token = root["root_folder"]["token"]

    result = call_feishu("create_feishu_document", {"title": title, "folderToken": folder_token})
    doc_id = (
        result.get("documentId")
        or result.get("data", {}).get("documentId")
        or result.get("document", {}).get("document_id", "")
    )
    if not doc_id:
        print(f"  创建文档失败: {json.dumps(result, ensure_ascii=False)[:300]}")
    return doc_id


def publish(md_text, doc_id=None, title="未命名文档"):
    """
    将 Markdown 文本发布到飞书文档。
    如果 doc_id 为空，创建新文档。
    返回 (doc_id, url)。
    """
    if not doc_id:
        doc_id = create_document(title)
        if not doc_id:
            return None, None

    print(f"  文档ID: {doc_id}")
    clear_document(doc_id)
    time.sleep(0.3)

    # 解析 markdown → segments
    segments = parse_markdown(md_text)
    print(f"  解析 {len(segments)} 个段落")

    index = 0
    ok = 0
    fail = 0

    for si, seg in enumerate(segments):
        if si % 20 == 0 and si > 0:
            print(f"  {si}/{len(segments)}...", end="\r")

        if seg['type'] == 'table':
            headers, rows = seg['headers'], seg['rows']
            if headers and rows:
                n = create_table(doc_id, index, headers, rows)
                if n > 0:
                    index += n; ok += n
                else:
                    fail += 1
            else:
                fail += 1
        elif seg['type'] == 'heading':
            block = {
                "blockType": "heading",
                "options": {"heading": {"level": seg['level'], "content": seg['content']}}
            }
            if create_blocks(doc_id, index, [block]):
                index += 1; ok += 1
            else:
                fail += 1
        elif seg['type'] == 'text':
            block = {
                "blockType": "text",
                "options": {"text": {"textStyles": parse_text_styles(seg['content'])}}
            }
            if create_blocks(doc_id, index, [block]):
                index += 1; ok += 1
            else:
                fail += 1
        elif seg['type'] == 'code':
            block = {
                "blockType": "code",
                "options": {"code": {"code": seg['content'], "language": 1, "wrap": True}}
            }
            if create_blocks(doc_id, index, [block]):
                index += 1; ok += 1
            else:
                fail += 1
        elif seg['type'] == 'list':
            blocks = []
            for item in seg['items']:
                blocks.append({
                    "blockType": "list",
                    "options": {"list": {"content": item, "isOrdered": seg.get('ordered', False)}}
                })
            if create_blocks(doc_id, index, blocks):
                index += len(blocks); ok += len(blocks)
            else:
                fail += len(blocks)
        elif seg['type'] == 'divider':
            block = {
                "blockType": "text",
                "options": {"text": {"textStyles": [{"text": "───"}], "align": 2}}
            }
            if create_blocks(doc_id, index, [block]):
                index += 1; ok += 1
            else:
                fail += 1

        time.sleep(0.12)

    url = f"https://bytedance.larkoffice.com/docx/{doc_id}"
    print(f"  {ok} 块成功, {fail} 失败 → {url}")
    return doc_id, url


def parse_markdown(md_text):
    """完整解析 Markdown 为段落列表"""
    segments = []
    lines = md_text.split('\n')
    i = 0

    while i < len(lines):
        line = lines[i]

        if not line.strip():
            i += 1
            continue

        # 代码块
        if line.strip().startswith('```'):
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code_lines.append(lines[i])
                i += 1
            i += 1
            segments.append({'type': 'code', 'content': '\n'.join(code_lines)})
            continue

        # 标题
        hm = re.match(r'^(#{1,6})\s+(.+)$', line)
        if hm:
            segments.append({'type': 'heading', 'level': min(len(hm.group(1)), 9), 'content': hm.group(2).strip()})
            i += 1
            continue

        # 水平线
        if re.match(r'^---\s*$', line):
            segments.append({'type': 'divider'})
            i += 1
            continue

        # 表格
        if line.strip().startswith('|'):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith('|'):
                table_lines.append(lines[i])
                i += 1
            headers, rows = parse_table('\n'.join(table_lines))
            segments.append({'type': 'table', 'headers': headers, 'rows': rows})
            continue

        # 引用
        if line.startswith('>'):
            quote_lines = []
            while i < len(lines) and lines[i].startswith('>'):
                quote_lines.append(lines[i][1:].strip())
                i += 1
            segments.append({'type': 'text', 'content': ' '.join(quote_lines)})
            continue

        # 无序列表
        ulm = re.match(r'^[-*]\s+(.+)', line)
        if ulm:
            items = []
            while i < len(lines):
                m = re.match(r'^[-*]\s+(.+)', lines[i])
                if not m: break
                items.append(m.group(1).strip())
                i += 1
            segments.append({'type': 'list', 'ordered': False, 'items': items})
            continue

        # 有序列表
        olm = re.match(r'^\d+\.\s+(.+)', line)
        if olm:
            items = []
            while i < len(lines):
                m = re.match(r'^\d+\.\s+(.+)', lines[i])
                if not m: break
                items.append(m.group(1).strip())
                i += 1
            segments.append({'type': 'list', 'ordered': True, 'items': items})
            continue

        # 普通文本段落
        text_lines = []
        while i < len(lines) and lines[i].strip() and not re.match(r'^(#{1,6}\s|---$|\||```|>|[-*]\s|\d+\.\s)', lines[i]):
            text_lines.append(lines[i].strip())
            i += 1
        if text_lines:
            segments.append({'type': 'text', 'content': ' '.join(text_lines)})

    return segments


def publish_file(md_path, title=None, doc_id=None):
    """从文件发布到飞书"""
    with open(md_path, 'r', encoding='utf-8') as f:
        md_text = f.read()
    if not title:
        title = os.path.basename(md_path).replace('.md', '')
    return publish(md_text, doc_id=doc_id, title=title)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='发布 Markdown 到飞书文档')
    parser.add_argument('input', help='Markdown 文件路径')
    parser.add_argument('--title', '-t', help='文档标题')
    parser.add_argument('--doc-id', '-d', help='更新已有文档（不创建新文档）')
    args = parser.parse_args()

    doc_id, url = publish_file(args.input, title=args.title, doc_id=args.doc_id)
    if url:
        print(f'\n{url}')
    else:
        print('\n发布失败')
        sys.exit(1)
