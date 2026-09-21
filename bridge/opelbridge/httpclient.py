"""Minimaler HTTP-Client auf urllib-Basis - keine externen Abhaengigkeiten."""
from __future__ import annotations

import gzip
import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

USER_AGENT = "OpelBridge/1.0 (+HuaweiWatchGT6)"


class HttpError(RuntimeError):
    def __init__(self, status: int, body: str, url: str):
        super().__init__("HTTP %s bei %s: %s" % (status, url, body[:300]))
        self.status = status
        self.body = body
        self.url = url


def request(
    method: str,
    url: str,
    *,
    headers: Optional[Dict[str, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    data: Optional[bytes] = None,
    json_body: Optional[Any] = None,
    form: Optional[Dict[str, Any]] = None,
    timeout: float = 20.0,
    retries: int = 2,
    verify: bool = True,
) -> Tuple[int, bytes]:
    if params:
        sep = "&" if "?" in url else "?"
        url = url + sep + urllib.parse.urlencode(
            {k: v for k, v in params.items() if v is not None}
        )
    hdrs = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Accept-Encoding": "gzip",
    }
    if json_body is not None:
        data = json.dumps(json_body).encode("utf-8")
        hdrs["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode("utf-8")
        hdrs["Content-Type"] = "application/x-www-form-urlencoded"
    if headers:
        hdrs.update(headers)

    ctx = ssl.create_default_context()
    if not verify:
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE

    last_error: Optional[Exception] = None
    for attempt in range(retries + 1):
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
                body = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
                return resp.status, body
        except urllib.error.HTTPError as exc:                      # 4xx / 5xx
            body = exc.read() or b""
            try:
                if exc.headers.get("Content-Encoding") == "gzip":
                    body = gzip.decompress(body)
            except OSError:
                pass
            if exc.code in (429, 500, 502, 503, 504) and attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                last_error = exc
                continue
            raise HttpError(exc.code, body.decode("utf-8", "replace"), url) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = exc
            if attempt < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise RuntimeError("Netzwerkfehler bei %s: %s" % (url, exc)) from exc
    raise RuntimeError("Netzwerkfehler bei %s: %s" % (url, last_error))


def get_json(url: str, **kwargs: Any) -> Any:
    _status, body = request("GET", url, **kwargs)
    return json.loads(body.decode("utf-8", "replace") or "null")


def post_json(url: str, **kwargs: Any) -> Any:
    _status, body = request("POST", url, **kwargs)
    text = body.decode("utf-8", "replace")
    if not text.strip():
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return {"raw": text}
