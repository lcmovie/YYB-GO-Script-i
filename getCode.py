"""YYB-Go-Enhanced compatibility layer for bundled mini-program scripts.

The only account variable is YYB_SERVER. Each non-empty line must be:
    server:port@ref
"""

from __future__ import annotations

import os
from typing import Any

import requests


def _entries() -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for line in os.getenv("YYB_SERVER", "").splitlines():
        value = line.strip()
        if not value or "@" not in value:
            continue
        server, ref = value.rsplit("@", 1)
        server, ref = server.strip().rstrip("/"), ref.strip()
        if server and ref:
            if not server.startswith(("http://", "https://")):
                server = "http://" + server
            result.append((server, ref))
    return result


def _install_legacy_account_view() -> None:
    """Let legacy loops read refs while YYB_SERVER remains the source of truth."""
    if not os.getenv("WX_ID"):
        refs = [ref for _, ref in _entries()]
        if refs:
            os.environ["WX_ID"] = "\n".join(refs)


_install_legacy_account_view()


def _select(identifier: str) -> tuple[str, str]:
    entries = _entries()
    if not entries:
        raise RuntimeError("未配置 YYB_SERVER，格式：地址@账号ref，多账号换行")
    raw = str(identifier or "").split("#", 1)[0].strip()
    for server, ref in entries:
        if raw in (ref, f"{server}@{ref}"):
            return server, ref
    if len(entries) == 1:
        return entries[0]
    raise RuntimeError(f"YYB_SERVER 中找不到账号ref：{raw}")


def _post(identifier: str, app_id: str, route: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    server, ref = _select(identifier)
    body: dict[str, Any] = {"ref": ref, "app_id": app_id}
    if payload is not None:
        body["payload"] = payload
    session = requests.Session()
    session.trust_env = False
    response = session.post(f"{server}{route}", json=body, timeout=30)
    try:
        data = response.json()
    except ValueError as exc:
        raise RuntimeError(f"YYB响应不是JSON（HTTP {response.status_code}）") from exc
    if response.status_code != 200 or data.get("code") != 0:
        raise RuntimeError(data.get("msg") or f"YYB请求失败（HTTP {response.status_code}）")
    result = ((data.get("data") or {}).get("result") or {})
    if not isinstance(result, dict):
        raise RuntimeError(f"YYB响应result格式错误：{str(result)[:120]}")
    return result


def get_single_code(app_id: str, identifier: str) -> str | None:
    try:
        code = _post(identifier, app_id, "/wxapp/getCode").get("code")
        if not code:
            raise RuntimeError("YYB未返回有效code")
        return str(code)
    except Exception as exc:
        print(f"[getCode] 获取code失败：{exc}")
        return None


def get_single_phone_number(app_id: str, identifier: str) -> str | None:
    try:
        code = _post(identifier, app_id, "/wxapp/getPhoneNumber").get("code")
        return str(code) if code else None
    except Exception as exc:
        print(f"[getCode] 获取手机号code失败：{exc}")
        return None


def get_single_operate_wx_data(
    app_id: str,
    identifier: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    try:
        if payload:
            return _post(identifier, app_id, "/wxapp/operateWxData", payload)
        code = get_single_code(app_id, identifier)
        return {"code": code, "encryptedData": None, "iv": None} if code else None
    except Exception as exc:
        print(f"[getCode] 获取operateWxData失败：{exc}")
        return None

