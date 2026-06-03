# 知行股票分析系统 — 测试指南

## 运行测试

```bash
cd 知行股票分析系统
pytest tests/ -v --tb=short
```

## 测试环境

- Python >= 3.11
- pytest >= 8.3.0
- 无需真实 iFind token（所有外部调用均已 mock）
- 使用临时 SQLite 数据库（每次测试后自动清理）

## 标准测试用例（TC-1 ~ TC-7）

| 用例 | 文件 | 目的 | Mock 范围 |
|------|------|------|----------|
| TC-1 | `test_indicators.py` | 单股指标计算，验证关键字段和B1信号触发 | 无（纯本地计算） |
| TC-2 | `test_sector_scan.py` | 板块B1扫描分类正确（B1/近B1/其他） | ensure_candles + get_sector_members |
| TC-3 | `test_portfolio.py` | 关注列表增查删 | 无（纯DB操作） |
| TC-4 | `test_portfolio.py` | 持仓+交易流水成本价和盈亏计算 | 无（纯DB操作） |
| TC-5 | `test_daily_review.py` | 日终追踪状态机转换 | 无（纯逻辑+DB） |
| TC-6 | `test_reporting.py` | 报告生成格式校验 | 无（纯本地生成） |
| TC-7 | `test_e2e.py` | 端到端：扫描→报告→飞书发布 | publish_report |

## Mock 策略

### mock ensure_candles

```python
def mock_ensure_candles(code, required_days=120):
    return [{"date": "...", "open": ..., "high": ..., "low": ..., "close": ..., "volume": ...}]

monkeypatch.setattr("storage.kline_filler.ensure_candles", mock_ensure_candles, raising=False)
```

### mock ifind_client.get_sector_members

```python
def mock_get_sector_members(name: str):
    return [StockInfo(code="000001", name="平安银行")]

monkeypatch.setattr("data_source.ifind_client.IFindClient.get_sector_members", mock_get_sector_members, raising=False)
```

### mock 飞书发布

```python
from reporting import feishu_publisher
feishu_publisher.publish_report = lambda path, title=None, folder_token=None: "https://feishu.cn/docx/123"
```

## 构造特定信号的 K 线

在 `conftest.py` 中提供了两个 fixture：
- `mock_candles_120`：一般震荡走势
- `mock_candles_for_b1`：低位缩量企稳，预期触发拐头B或超缩量

如需构造其他信号（如缩爆B1），可参考 `indicators/suo_bao_b1.py` 的判定条件构造爆量+缩量走势。

## 新增测试

1. 在 `tests/` 下新建 `test_xxx.py`
2. 在文件头部加入 `sys.path.insert` 确保能导入项目代码
3. 使用 `temp_db` fixture 获取临时数据库
4. 使用 `monkeypatch` mock 外部依赖
5. 运行 `pytest tests/test_xxx.py -v` 验证
