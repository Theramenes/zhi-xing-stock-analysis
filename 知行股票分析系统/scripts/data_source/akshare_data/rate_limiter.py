"""
akshare 防封限速器 — 抄 JusticePlutus AkshareFetcher 防封策略
"""
import random
import time
import functools

# User-Agent 池
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Version/17.2 Safari/605.1.15',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36',
]

# 速率限制
_MAX_CALLS_PER_MINUTE = 30
_call_timestamps: list[float] = []

# 熔断器
_CONSECUTIVE_FAILURES = 0
_CIRCUIT_OPEN_UNTIL = 0.0


def _enforce_rate_limit():
    """每分钟最多 N 次调用，超出等下一分钟"""
    global _call_timestamps
    now = time.time()
    _call_timestamps = [t for t in _call_timestamps if now - t < 60]
    if len(_call_timestamps) >= _MAX_CALLS_PER_MINUTE:
        wait = 60 - (now - _call_timestamps[0]) + 1
        time.sleep(wait)
    _call_timestamps.append(time.time())


def _check_circuit():
    """检查熔断器是否打开"""
    global _CIRCUIT_OPEN_UNTIL
    if _CIRCUIT_OPEN_UNTIL > time.time():
        raise RuntimeError(f"akshare 熔断中，{_CIRCUIT_OPEN_UNTIL - time.time():.0f}s 后恢复")
    return True


def with_rate_limit(func):
    """装饰器：随机休眠 + 速率限制 + 指数退避重试 + 熔断"""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        _check_circuit()
        global _CONSECUTIVE_FAILURES

        last_err = None
        for attempt in range(3):
            try:
                _enforce_rate_limit()
                # 随机休眠 1.5-4s (抄 JusticePlutus 2-5s，适度降低)
                time.sleep(random.uniform(1.5, 4.0))
                result = func(*args, **kwargs)
                _CONSECUTIVE_FAILURES = 0  # 成功就重置
                return result
            except Exception as e:
                last_err = e
                _CONSECUTIVE_FAILURES += 1
                wait = 2 ** attempt * random.uniform(1, 3)
                if attempt < 2:
                    time.sleep(wait)

        # 3次失败，开熔断
        if _CONSECUTIVE_FAILURES >= 3:
            global _CIRCUIT_OPEN_UNTIL
            _CIRCUIT_OPEN_UNTIL = time.time() + 300
            raise RuntimeError(f"akshare 连续失败{_CONSECUTIVE_FAILURES}次，熔断300s")
        raise last_err

    return wrapper
