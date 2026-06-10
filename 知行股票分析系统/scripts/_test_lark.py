import sys,io; sys.stdout=io.TextIOWrapper(sys.stdout.buffer,encoding='utf-8')
sys.path.insert(0,'.')
from reporting.feishu_publisher import _sanitize_lark_md

test = '| 代码 | 信号 |\n|------|------|\n| 000021 | ["回踩白线B"] |\n| 000582 | ["原始B1", "回踩黄线B"] |\n| 000404 | ["超卖缩量拐头B", "超卖缩量B", "超卖超 |'
print('=== BEFORE ===')
print(test)
print()
print('=== AFTER ===')
print(_sanitize_lark_md(test))

test2 = '## 标题\n\n文字\n\n| 指数 | 收盘 |\n|------|------|\n| 上证 | 4010 |\n| 深证 | 15268 |\n\n文字 after table'
print()
print(_sanitize_lark_md(test2))
