"""
掘金 MyQuant K 线 Fetcher — subprocess 调用 Python 3.10 (gm SDK 不支持 3.14)

通过 subprocess + stdin JSON 传入参数，stdout 返回 JSON candles，
避免 import gm.api 导致 3.14 下崩溃。

环境变量:
  ZX_MYQUANT_TOKEN  — 掘金 Token
  ZX_MYQUANT_PYTHON — Python 3.10/3.11/3.12/3.13 解释器路径，默认 D:/Development/Python/python.exe
"""
import json
import os
import subprocess
from typing import Optional, List

_PYTHON = os.environ.get("ZX_MYQUANT_PYTHON", "").strip()
if not _PYTHON:
    for candidate in [
        r"D:\Development\Python\python.exe",
        r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python313\python.exe",
        r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python312\python.exe",
        r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python311\python.exe",
        r"C:\Users\Theramenes\AppData\Local\Programs\Python\Python310\python.exe",
    ]:
        if os.path.exists(candidate):
            _PYTHON = candidate
            break


def _to_myquant_symbol(code: str) -> str:
    """002693 → SZSE.002693, 600276 → SHSE.600276"""
    prefix = "SHSE" if code.startswith(("5", "6", "9")) else "SZSE"
    return f"{prefix}.{code}"


class MyQuantFetcher:
    """掘金 K 线 Fetcher"""

    name = "myquant"
    priority = 1

    def __init__(self):
        self._token = os.environ.get("ZX_MYQUANT_TOKEN", "").strip()
        self._ready = _PYTHON and os.path.exists(_PYTHON) and bool(self._token)

    def is_available(self) -> bool:
        return self._ready

    def get_kline_batch(self, codes: List[str], start_date: str, end_date: str) -> dict:
        """批量拉取K线。脚本写入临时文件执行，避免 -c 长度/PIPE 截断。"""
        if not self._ready:
            return {}
        import tempfile, atexit
        token = self._token

        lines = ["from gm.api import *", f"set_token('{token}')", "import json", "results = {}"]
        for code in codes:
            symbol = _to_myquant_symbol(code)
            lines.append(
                f"try:\n"
                f"    data = history(symbol='{symbol}', frequency='1d',"
                f" start_time='{start_date}', end_time='{end_date}',"
                f" fields='eob,open,high,low,close,volume', adjust=ADJUST_PREV, df=True)\n"
                f"    results['{code}'] = [{{'date':str(r.eob)[:10],'open':r.open,"
                f"'high':r.high,'low':r.low,'close':r.close,'volume':int(r.volume)}}"
                f" for _,r in data.iterrows()] if data is not None and not data.empty else []\n"
                f"except Exception as e:\n    results['{code}'] = []\n"
            )
        lines.append("print(json.dumps(results, ensure_ascii=False))")
        script = "\n".join(lines)

        tmpdir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_mq_tmp")
        os.makedirs(tmpdir, exist_ok=True)
        tmpf = tempfile.NamedTemporaryFile(mode="w", suffix=".py", dir=tmpdir, delete=False, encoding="utf-8")
        tmpf.write(script)
        tmpf.close()

        try:
            r = subprocess.run(
                [_PYTHON, "-u", tmpf.name],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, timeout=600,
            )
            os.unlink(tmpf.name)
            if r.returncode != 0 or not r.stdout.strip():
                return {}
            data = json.loads(r.stdout.strip())
            result = {}
            for code, candles in data.items():
                for c in candles:
                    vol = abs(c.get("volume", 0))
                    c["volume"] = vol / 100 if vol > 100000 else vol
                result[code] = candles if candles else None
            return result
        except subprocess.TimeoutExpired:
            try: os.unlink(tmpf.name)
            except: pass
            return {}
        except Exception:
            try: os.unlink(tmpf.name)
            except: pass
            return {}

    def get_kline(self, code: str, start_date: str, end_date: str) -> Optional[List[dict]]:
        if not self._ready:
            return None

        symbol = _to_myquant_symbol(code)
        script = (
            "from gm.api import *\n"
            f"set_token('{self._token}')\n"
            "import json, sys\n"
            f"data = history(symbol='{symbol}', frequency='1d',"
            f" start_time='{start_date}', end_time='{end_date}',"
            " fields='eob,open,high,low,close,volume', adjust=ADJUST_PREV, df=True)\n"
            "if data is None or data.empty:\n"
            "    print('[]')\n"
            "else:\n"
            "    result = [{'date':str(r.eob)[:10],'open':r.open,'high':r.high,"
            "               'low':r.low,'close':r.close,'volume':int(r.volume)}"
            "              for _,r in data.iterrows()]\n"
            "    print(json.dumps(result, ensure_ascii=False))\n"
        )

        try:
            r = subprocess.run(
                [_PYTHON, "-u", "-c", script],
                stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, timeout=30,
            )
            if r.returncode != 0 or not r.stdout.strip():
                return None
            # 只取最后一行 JSON（忽略 print 等噪音）
            lines = [l for l in r.stdout.strip().split("\n") if l.strip().startswith("[")]
            if not lines:
                return None
            try:
                candles = json.loads(lines[-1])
            except json.JSONDecodeError:
                return None
            # 标准化 volume
            for c in candles:
                vol = abs(c.get("volume", 0))
                c["volume"] = vol / 100 if vol > 100000 else vol
            return candles if candles else None
        except subprocess.TimeoutExpired:
            return None
        except Exception:
            return None
