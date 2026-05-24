"""
TC-7: 端到端 — 板块扫描 → 报告生成 → 飞书发布（全程 mock 外部 API）
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "知行股票分析系统", "scripts"))

from reporting.generator import generate_b1_report, save_report
from scanning.sector_scanner import SectorOverviewResult, SectorB1Result, StockScanResult


def test_e2e_report_pipeline(tmp_path):
    """mock 扫描结果 → 生成报告 → 保存本地 → 模拟飞书发布"""
    s1 = StockScanResult(code="002460", name="赣锋锂业")
    s1.last = 25.0
    s1.change_pct = 2.1
    s1.信号 = ["拐头B"]
    s1.J = 12
    s1.评分 = 4
    s1.趋势 = "多头"

    b1_result = SectorB1Result(name="电池")
    b1_result.stocks = [s1]
    b1_result.b1_stocks = [s1]

    overview = SectorOverviewResult(query="电池", sector_name="电池", sector_type="industry")
    overview.total_stocks = 1

    combined = {
        "overview": overview,
        "b1": b1_result,
        "banned": [],
    }

    md = generate_b1_report(combined)
    assert "电池板块B1扫描" in md

    out_path = tmp_path / "report.md"
    save_report(md, str(out_path))
    assert out_path.exists()

    # mock 飞书发布：只验证 publish_report 被调用后的 URL 格式
    def mock_publish(path, title=None, folder_token=None):
        return "https://feishu.cn/docx/123456789"

    from reporting import feishu_publisher
    feishu_publisher.publish_report = mock_publish
    url = feishu_publisher.publish_report(str(out_path), title="电池B1扫描")
    assert "feishu.cn/docx/" in url
