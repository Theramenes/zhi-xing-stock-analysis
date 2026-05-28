"""
数据源配置 — 纯 Python 内嵌，无外部 CLI 依赖

数据源优先级（环境变量控制）:
  ZX_DATA_SOURCE     → 强制数据源: ifind_http | efinance | akshare | auto
  ZX_IFIND_REFRESH_TOKEN → iFind HTTP API Token（可选，用于专业数据增强）
"""
import os


class DataSourceConfig:
    def __init__(self):
        # iFind HTTP API Token（可选，不配也能用免费源）
        self.ifind_refresh_token = os.environ.get("ZX_IFIND_REFRESH_TOKEN", "")

        # 强制数据源（ifind_http / efinance / akshare / auto）
        self.force_source = os.environ.get("ZX_DATA_SOURCE", "auto")

    def available_sources(self):
        """返回可用的数据源列表"""
        sources = ["local", "efinance", "akshare", "baostock"]
        if self.ifind_refresh_token:
            sources.append("ifind_http")
        return sources

    def __repr__(self):
        return (
            f"DataSourceConfig(available={self.available_sources()}, "
            f"force={self.force_source})"
        )


# 全局单例
config = DataSourceConfig()
