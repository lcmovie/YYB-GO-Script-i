"""青龙统一通知兼容层：Server酱、PushPlus、企业微信机器人。"""

from __future__ import annotations

import os
from typing import Any

import requests


def _post(url: str, **kwargs: Any) -> Any:
    session = requests.Session()
    session.trust_env = False
    response = session.post(url, timeout=20, **kwargs)
    response.raise_for_status()
    try:
        return response.json()
    except ValueError:
        return response.text


def send(title: str, content: str = "") -> None:
    title, content = str(title), str(content or "")
    print(f"\n============== 通知 ==============\n{title}\n{content}")
    configured = 0

    push_key = os.getenv("PUSH_KEY", "").strip()
    if push_key:
        configured += 1
        try:
            base = "https://sctapi.ftqq.com" if push_key.startswith("sctp") else "https://sc.ftqq.com"
            _post(f"{base}/{push_key}.send", data={"title": title, "desp": content})
        except Exception as exc:
            print(f"[通知失败] Server酱: {exc}")

    token = os.getenv("PUSH_PLUS_TOKEN", "").strip()
    if token:
        configured += 1
        try:
            payload = {"token": token, "title": title, "content": content, "template": "txt"}
            topic = os.getenv("PUSH_PLUS_USER", "").strip()
            if topic:
                payload["topic"] = topic
            _post("https://www.pushplus.plus/send", json=payload)
        except Exception as exc:
            print(f"[通知失败] PushPlus: {exc}")

    qywx_key = os.getenv("QYWX_KEY", "").strip()
    if qywx_key:
        configured += 1
        try:
            _post(
                f"https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key={qywx_key}",
                json={"msgtype": "text", "text": {"content": f"{title}\n{content}"}},
            )
        except Exception as exc:
            print(f"[通知失败] 企业微信: {exc}")

    if not configured:
        print("未配置 PUSH_KEY、PUSH_PLUS_TOKEN 或 QYWX_KEY，仅输出日志")


sendNotify = send
send_notify = send
