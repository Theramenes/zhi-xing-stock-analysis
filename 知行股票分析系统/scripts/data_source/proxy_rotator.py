"""
代理轮转引擎 — 抄自 VeKiner/akshare-stock-data-fetcher 的 build_rotating_get

零侵入：用 unittest.mock.patch 替换 akshare 内部的 requests.get，走动态代理池。
不配代理时返回直连函数，不影响现有流程。

环境变量:
  ZX_PROXY_API_URL  — 代理 API 地址（不配则不启用）
  ZX_PROXY_FORMAT   — 返回格式: ip_port / ip_port_user_pass / json_ip / json_proxies
                      默认 ip_port_user_pass
"""
import os
import random
import time
from typing import Callable, Optional, List, Dict

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# 东财验证 URL — 能连通这个 = 代理可用来拉东财数据
EASTMONEY_TEST_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
EASTMONEY_TEST_PARAMS = {
    "fields1": "f1,f2", "fields2": "f51,f52",
    "beg": "20260501", "end": "20260530", "rtntype": 6,
    "secid": "0.002693", "klt": 101, "fqt": 1,
}

UA_LIST = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/68.0.3440.106 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; …) Gecko/20100101 Firefox/61.0",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/62.0.3202.62 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
]


def _parse_proxy(raw: str, fmt: str) -> Optional[Dict[str, str]]:
    """将 API 返回的原始字符串解析为 requests 代理字典"""
    raw = raw.strip()
    if not raw:
        return None

    if fmt == "json_proxies":
        # 已经是拼好的格式 {"http": "...", "https": "..."}
        import json
        try:
            return json.loads(raw)
        except Exception:
            return None

    if fmt == "json_ip":
        import json
        try:
            obj = json.loads(raw)
            host = str(obj.get("ip", obj.get("host", "")))
            port = str(obj.get("port", ""))
            user = str(obj.get("user", obj.get("username", "")))
            pwd = str(obj.get("pass", obj.get("password", "")))
        except Exception:
            return None
    else:
        parts = raw.split(":")
        if fmt == "ip_port" and len(parts) >= 2:
            host, port = parts[0], parts[1]
            user, pwd = "", ""
        elif fmt == "ip_port_user_pass" and len(parts) >= 4:
            host, port, user, pwd = parts[0], parts[1], parts[2], parts[3]
        else:
            return None

    if not host or not port:
        return None
    auth = f"{user}:{pwd}@" if user and pwd else ""
    proxy_url = f"http://{auth}{host}:{port}/"
    return {"http": proxy_url, "https": proxy_url}


def _test_proxy(proxy: Dict[str, str], timeout: float = 6) -> bool:
    """用东财API测试代理是否可用"""
    try:
        s = requests.Session()
        s.trust_env = False
        s.proxies.update(proxy)
        s.headers.update({
            "User-Agent": random.choice(UA_LIST),
            "Connection": "close",
            "Referer": "https://quote.eastmoney.com/",
        })
        r = s.get(EASTMONEY_TEST_URL, params=EASTMONEY_TEST_PARAMS, timeout=timeout)
        s.close()
        return r.status_code == 200
    except Exception:
        return False


def fetch_proxies(api_url: str, fmt: str, count: int = 2, timeout: float = 6) -> List[Dict[str, str]]:
    """从代理 API 拉取并验证代理列表"""
    proxies = []
    attempts = count * 3
    for _ in range(attempts):
        if len(proxies) >= count:
            break
        try:
            resp = requests.get(api_url, timeout=10)
            resp.raise_for_status()
            for line in resp.text.strip().split("\n"):
                if len(proxies) >= count:
                    break
                p = _parse_proxy(line if "\n" in resp.text else resp.text, fmt)
                if p and _test_proxy(p, timeout):
                    proxies.append(p)
        except Exception:
            pass
        time.sleep(0.5)
    return proxies


def build_rotating_get(
    proxies_supplier: Callable[[], List[Dict[str, str]]],
    timeout: float = 20,
    per_proxy_retries: int = 1,
    backoff: tuple = (0.4, 1.0),
    include_direct: bool = True,
    max_supplier_refresh: int = 3,
) -> Callable:
    """构建代理轮转 GET 函数。

    返回的 rotating_get(url, **kwargs) 签名与 requests.get 兼容，
    可直接用 unittest.mock.patch('requests.get', rotating_get) 替换。

    轮转逻辑:
      1. 从 proxies_supplier 获取代理池（含直连兜底）
      2. random.shuffle 打乱
      3. 逐个尝试，成功则返回 response
      4. 全部失败 → 刷新代理池 → 重试（最多 max_supplier_refresh 轮）
      5. 仍然失败 → raise last exception
    """
    retriable = (
        requests.exceptions.ProxyError,
        requests.exceptions.ConnectTimeout,
        requests.exceptions.ReadTimeout,
        requests.exceptions.SSLError,
        requests.exceptions.ConnectionError,
        requests.exceptions.ChunkedEncodingError,
    )

    ua = random.choice(UA_LIST)

    def rotating_get(url, **kwargs):
        last_exc = None
        for refresh_round in range(max_supplier_refresh + 1):
            try:
                pool = proxies_supplier() or []
            except Exception as e:
                pool = []
                last_exc = e

            if include_direct:
                pool = list(pool) + [None]  # None = 直连
            random.shuffle(pool)

            for proxy in pool:
                s = requests.Session()
                try:
                    s.trust_env = False
                    s.headers.update({
                        "User-Agent": ua,
                        "Accept": "*/*",
                        "Connection": "close",
                        "Referer": "https://quote.eastmoney.com/",
                    })
                    if proxy:
                        s.proxies.update(proxy)

                    retry = Retry(
                        total=per_proxy_retries,
                        connect=per_proxy_retries,
                        read=per_proxy_retries,
                        backoff_factor=0.5,
                        status_forcelist=[429, 500, 502, 503, 504],
                        allowed_methods=["GET"],
                        respect_retry_after_header=True,
                        raise_on_status=False,
                    )
                    adapter = HTTPAdapter(
                        max_retries=retry, pool_connections=1, pool_maxsize=1
                    )
                    s.mount("http://", adapter)
                    s.mount("https://", adapter)

                    req_kwargs = dict(kwargs)
                    req_kwargs.setdefault("timeout", timeout)
                    resp = s.get(url, **req_kwargs)
                    resp.raise_for_status()
                    return resp
                except retriable as e:
                    last_exc = e
                    time.sleep(random.uniform(*backoff))
                finally:
                    try: s.close()
                    except Exception: pass

        if last_exc:
            raise last_exc
        raise RuntimeError("代理轮转请求失败且无可用代理")

    return rotating_get


def create_rotating_get() -> Optional[Callable]:
    """对外接口：从环境变量读配置，创建代理轮转函数。
    不配 ZX_PROXY_API_URL 则返回 None（不启用代理轮转）。
    """
    api_url = os.environ.get("ZX_PROXY_API_URL", "").strip()
    if not api_url:
        return None

    fmt = os.environ.get("ZX_PROXY_FORMAT", "ip_port_user_pass").strip()
    count_str = os.environ.get("ZX_PROXY_COUNT", "2").strip()
    try:
        count = int(count_str)
    except ValueError:
        count = 2

    def supplier():
        return fetch_proxies(api_url, fmt, count=count)

    return build_rotating_get(
        proxies_supplier=supplier,
        timeout=20,
        per_proxy_retries=1,
        backoff=(0.4, 1.0),
        include_direct=True,
        max_supplier_refresh=3,
    )
