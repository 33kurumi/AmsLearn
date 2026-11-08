#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""AmsLearn 三端联调验收脚本（仅使用 Python 标准库 urllib）。

用途
  按 docs/开发过程/01-接口约定.md 与 PRD 8.1~8.3，对 Java 业务服务、AI 服务、前端页面做
  自动化冒烟验收，输出 PASS/FAIL/SKIP 表并返回退出码，供课程答辩与集成验收使用。

用法
  python scripts/acceptance_check.py
  python scripts/acceptance_check.py --base-java http://localhost:8080 --base-ai http://localhost:8000
  python scripts/acceptance_check.py --base-web http://localhost:5173 --verbose
  python scripts/acceptance_check.py --skip-web

参数
  --base-java  Java 业务服务地址，默认 http://localhost:8080
  --base-ai    FastAPI AI 服务地址，默认 http://localhost:8000
  --base-web   前端地址，默认 http://localhost:5173（并行开发期可用 --base-web http://localhost:5174）
  --skip-web   跳过前端页面检查（只测两个后端）
  --verbose    打印失败/关键响应的摘要
  --timeout   普通接口超时秒数，默认 20

退出码
  0  全部 PASS
  1  存在 FAIL（验收不通过）
  3  无 FAIL 但存在 SKIP（服务未全部启动 / 前置用例未执行，Not Ready）

说明
  - 本脚本会临时修改 teacher1 的班级配置（最大难度、禁用话题），结束时自动恢复原值；
    若恢复失败会打印醒目提示，请在教师端配置页手工核对。
  - 「作业题只给思路」为启发式判定：回答不含“答案是/答案为/正确答案是/故选 A/最终答案：”
    等直接给答案话术（拒绝话术中的“不能直接给出最终答案”不算泄漏）。
  - 未启动或不可达的服务不会抛异常中断脚本：相关用例标记 SKIP 并继续执行其余检查，
    全部跑完后统一输出 PASS/FAIL/SKIP 表；只有「服务可达但行为不符合契约」才判 FAIL。
  - C-16（v1.3）验证教师禁用话题的新流程：不再直接硬拦截，而是返回 3 道前置自测题，
    脚本会自适应地枚举选项直到 2/3 通过，再校验「第 1 步」循序渐进讲解与章节引用来源。
  - C-21（v1.3）用内嵌的题目 PNG 调图片答疑接口，校验视觉识别文本与后续文字答疑链路；
    若未配置识图模型则判 SKIP（Not Ready），不判 FAIL。
  - C-22（v1.4）注册唯一用户名（带时间戳后缀）的学生账号，校验「注册即登录」、默认班级
    C-GS-01、A2 当前用户与 S1 首页/S2 掌握度 67 条且 mastery=0；再以同名注册断言 409，
    非法用户名/密码断言 400。
  - C-23（v1.4）用 teacher1 重置 C-22 新学生的密码，断言旧密码登录 401、新密码登录 200，
    并覆盖 A20 边界：无 token 401、学生 token 403、跨班 403、不存在 404、密码过短 400。
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
import urllib.error
import urllib.request

ACCEPTANCE_REPLY = "该内容超出当前教学范围，暂时无法解答。"
CONFIG_FIELDS = ("answerMode", "maxDifficulty", "knowledgeScope", "boundaryRules", "kbAccess", "disabledTopics")


def setup_console() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


def display_width(text: str) -> int:
    width = 0
    for ch in str(text):
        width += 2 if ord(ch) > 127 else 1
    return width


def pad(text: str, width: int) -> str:
    text = str(text)
    return text + " " * max(0, width - display_width(text))


class ApiError(Exception):
    """服务可达，但响应/业务不符合契约，应判 FAIL。"""


class Skip(Exception):
    """服务不可达或前置用例未完成，应判 SKIP 而不是 FAIL。"""


def request(method: str, url: str, body=None, token=None, timeout=20.0, accept="application/json"):
    """发一个 HTTP 请求，返回 (status, payload, text)。HTTP 4xx/5xx 不抛异常。"""
    data = None
    headers = {"Accept": accept}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json; charset=utf-8"
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            return resp.status, safe_json(text), text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return exc.code, safe_json(text), text
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise Skip("服务未启动或不可达：%s（%s）" % (url, reason)) from exc


def safe_json(text: str):
    if not text:
        return None
    try:
        return json.loads(text)
    except Exception:
        return None


def request_multipart(url: str, filename: str, content: bytes, token=None,
                      timeout=120.0, field="file", content_type="image/png"):
    """上传单个文件（multipart/form-data），返回 (status, payload, text)。"""
    boundary = "----AmsLearnAcceptanceBoundary7f3c"
    head = (
        "--%s\r\n"
        'Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
        "Content-Type: %s\r\n\r\n" % (boundary, field, filename, content_type)
    ).encode("utf-8")
    tail = ("\r\n--%s--\r\n" % boundary).encode("utf-8")
    data = head + content + tail
    headers = {
        "Accept": "application/json",
        "Content-Type": "multipart/form-data; boundary=" + boundary,
    }
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
            return resp.status, safe_json(text), text
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", "replace")
        return exc.code, safe_json(text), text
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        reason = getattr(exc, "reason", None) or exc
        raise Skip("服务未启动或不可达：%s（%s）" % (url, reason)) from exc


# C-21 用的测试图片（1000x300 PNG，白底黑字：极限 lim(x→0) sin3x/x 与 ∫ x^2 e^x dx）。
# 内嵌 base64 以保证脚本可离线运行，无需额外图片文件。
VISION_TEST_PNG_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAA+gAAAEsCAIAAADfJw44AABFu0lEQVR42u3dd2DN1//48XOzB0Fi1SgVo4SqmNXaFI1dFLVH"
    "bIIqQlVqhVJqFI0dBDViz9okiNhqz9CoEGTv3x/nm/O7n9zk5mZKeD7+evfec9/3PY709T73dV5Hk5CQIAAAAADkbEZcAgAA"
    "AIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAACBwBwAAAEDgDgAA"
    "AIDAHQAAACBwBwAAAEDgDgAAAIDAHQAAACBwBwAAAEDgDgAAAIDAHQAAACBwBwAAAEDgDgAAABC4AwAAACBwBwAAAEDgDgAA"
    "ABC4AwAAACBwBwAAAEDgDgAAABC4AwAAACBwBwAAAAjcAQAAABC4AwAAACBwBwAAAAjcAQAAABC4AwAAACBwBwAAAAjcAQAA"
    "ABC4AwAAACBwBwAAAAjcAQAAABC4AwAAAATuAAAAAAjcAQAAABC4AwAAAATuAAAAAAjcAQAAABC4AwAAAATuAAAAAAjc34mr"
    "V6+amJhoNBorK6vbt28b8pFjx45pNBqNRmNjY/Ps2TOuIQAAAN7zwP3Ro0cNGjS4efNm+j4+ZcoUGUCXLVs23cfg4uISFxcn"
    "hJg5c2b58uUN+cjkyZPlhpubW7FixehnqWrVqpVGozExMfmgzvrMmTOaRFFRUR/aTT9x4kSDBg3Onj2r+1ZAQICrq2uDBg0S"
    "EhL41wEAQC4I3C9cuFCnTp0TJ040a9bs0aNH7+QYtm7deuTIESFEgwYNRowYYchH9uzZc/LkSSFElSpVhg8f/oH3sIcPH6rY"
    "lH9vSahfY+zs7MzNzT+oc4+JiRkyZMiJEyfq1Knj6uqq/VZISEjFihVnzpx54sQJb29v+gkAALkgcL906VJgYKAQIiAgoGnT"
    "pnI7Oz19+nTgwIFy+/jx40ZGRpqU1alTRwgRERGhgvWrV6+amppq9CpatKhsLLNxso0a2/b29s7grgYNGiSyeCQ+HWrUqCFS"
    "+x1Gj40bNwoh9u/fn75vP3XqlIEdTG5k3c8y0dHRr169evTo0fXr18+cObN3797169cvWrRoypQpQ4cO/e677+rXr1+2bNmi"
    "RYvKn5Wyzdy5c69fvy6EMDIyatOmjfZbefPm7d69u9yeNm0ag+4AAPxfuJiTD65fv35Pnjxxc3MTQty9e7d58+bHjx/Pnz9/"
    "9nx7fHx89+7dX758maZP/fzzzw8ePKBjQaRlxD2LAvf4+Hg7O7vQ0FBDGl++fNnR0XHRokXp/pnIy8urS5cuhrS8fv36lClT"
    "5PaQIUPkQ6+2H3/8cfny5bGxsf7+/itXruzXrx+9BQCAnJ5SPGXKlICAgBUrVgghrly50qpVq0OHDllaWmbDV7u4uBw7dkwI"
    "0bdv365duwohdu3atWDBgp9//vmrr77SbZ8vX75Dhw7NmTNHCFG4cOG1a9caGxsLIbZs2bJs2bLRo0e3bNlS91PvPEEiX758"
    "VatWFckNBgcFBckGpUuX1rOHkiVLZt3hffrpp/IwQkND5QCtjY1NxYoVU2r/5MkTGQ0bkplTvnz5JAfv6+sbFhYmfwDRfr1M"
    "mTI1a9ZMdYc+Pj6PHz8WaflJJ0sDdyMjo+rVqx8/ftyQxqdPn3Z0dBTZkiTTq1cvmdNfsmTJGTNm6Lb55JNPhgwZsmDBAiHE"
    "+PHj27dvb2try99rAACBe063dOnSZ8+e7du3T8YWnTt39vb2ljFx1vnll18WLlwohGjSpMmyZctMTEweP368ZMkSIcTChQu7"
    "deumO0v18ePHrVu3lj/rz58/v3nz5kKIgIAAT09P+ak6dep06tQppW88e/as4SkBv//++7p16+T2+fPn03GCKq5t1KjRpUuX"
    "dBt8+eWXMmIeP378+PHjU93hV199dfr0aSHE0aNHGzZsmFk3Qj4IyZD6iy++EEJUr15dzjpI1ueffy4D96ZNm6a688GDB7u4"
    "uKj/fPPmTeHChYUQxsbG9erV027ZqFGj5cuXp7rDLl26pClwz+oRdyFE8+bN37x5kzdv3rx58+bLl8/GxmbZsmVCiAIFCixa"
    "tMjW1rZAgQIFCxYsVKiQjY2N9gcrVKjw+eefG/IVZ8+effjwoeGHNG7cuAsXLsjtJUuW5M2bN9lmbm5uGzZsCAoKCgoKGjBg"
    "wNatW/l7DQD40CXkBsHBwfb29uqYf/rpJwM/+PPPP8uP2NvbG/517u7u8lPlypV79eqVen3evHkicfz1+fPnSY7QwcFBhUra"
    "bx04cEAOq5uYmHh7e2fKBRkzZkyW3kE5o1Tu/86dO4Z85Msvv5Ttjx49qv26duKQno87OTnJiDmlBj4+PnInjRs3TqnN/v37"
    "ZRsLC4vAwMBUe8W8efO0X1+zZo18vVmzZvIV+bgohOjXr58hF+G7776T7U+ePGlIewOLFKXPxYsXk/1S+W7x4sWTfVc+rwoh"
    "xowZY2Bv6dWrl0hMlUm18Y4dO9QR9uzZU3/jVatWqcaLFy9OAADgw5Y76rjnz59/+/btVlZWQoiGDRtqj5Jmrri4uKFDh8oB"
    "5mLFiu3Zs6dAgQJCK3mmW7duQoj79+//+uuv2h8MCgqSkW7BggVXrlyp/dbXX3/t6emp0WhiY2Pd3d3j4+Nz/gXfuHGjjPCq"
    "VauWkUqaWUFPDszs2bPlRp8+fYoUKZLWPW/ZskVuyMwokY057h+I69ev9+jRQ25XqVJF/oSlR+/evdu3by+3R40adfjwYYZa"
    "AACCVJmcr0qVKsuXLz98+PDSpUtNTU2z6Ftu3ry5YcMGIUTJkiWPHDmiG7N6eHjcuHGjUaNGalReKlu27Pnz5/v16/f999/r"
    "pj106tTp7t27J0+e3Lx5s5FRLnhY8vLykhudO3fOiv2rvBfdB6ckcXlwcLCcjqyGilPKkvL395cpNMbGxmPHjk3rIb19+/bg"
    "wYNCCHNz8w4dOmTDRX779q2aNmpmZpbp5TJzWk8LCgpq3br127dvhRD58uXbtm2bfBTX788//zx37tzTp0+jo6M7dOhw/Pjx"
    "atWq8YcbAEDgntN17do1q4dCHRwcTp06NXDgQE9Pz08++UQIkT9//jdv3gidOpUqbSYJGfenRKbz+vj46JbRyDn++eefy5cv"
    "y+2OHTvmkKOKjY3VH7jPmjVLbnz33Xfy3qXJrl275HTJli1b5suXL8m7K1askDOkRaYWG9W+5mXKlHmP/9CEhIS0bNlS5k1p"
    "NJq1a9ca+EtOwYIFd+zYUb9+/fDw8JCQkKZNm+7du7d27dr87QYAELjj/2L3D/kKLF26VG5kXZ5MoUKFVGK0tHv37pcvX2o0"
    "mp49e2q/bmZmJhIH4+XGq1evdHf44MEDNXlx3Lhx6Tikv/766x3myXz00UfvcY+KiIho27atn5+f/M+JEycmKdyuX/Xq1T09"
    "PTt16hQfH//q1asmTZps3bpVTv4GAIDAHUlVqlRp/fr1GdzJ4sWLDalMkg6ybEimpEa8efNG5ehfvHhRf/7G1KlTJ02alI5v"
    "sbe3X716tdBaJEjOJTAyMtJ+XSQ34n7+/Pnnz58nSWGfM2eOjOydnJw+++wzkfbx4AMHDggh8uTJ06pVK90G5cqVq1u3bqr7"
    "OX78uOH1VdSIe/78+bOnwuk7ERoa2rp1a1lZVQgxYMCAX375Ja076dChw/Lly+UU4bCwMCcnJzc3N1dXVwPzixYtWjRjxoy4"
    "uDgXF5cJEybwBw0AQOD+PrO0tDSwNJ4e6ZguKQyrC9SxY8fQ0NAVK1ZUqlQpg3vz8PAwcL2eTHTmzJnw8HCR2qitSFxUaNeu"
    "Xf3791dvvXz5UpUfMaRypa4dO3ZERkYKIdq2bZts4nX9+vUNLAdpeOCuRtyzbrj92LFjjRo1SumxIUnU6+TktHv37sw9gJcv"
    "X7Zu3VpVBOrevfvSpUvTl83fp0+fhISEAQMGxMfHx8XFTZo06eTJkx4eHqkuI3Dq1Cm1pJSrq6uDg0OaxvsBAMg5cuhEydWr"
    "V6e0mLx2bFG6dGn9K8/LVVeFEPfu3Ut1mfpMj1pEdi0df/jwYV9f32rVqk2bNi0mJkZkoKiOqgZYrFixqinIkyePSK3AS5oY"
    "Ui1EBtbif9NaRGKCuArr69Wrl+S21qhRQ+S8PBntEff3NU/m9u3bderUUVF7x44dV69enZHfhfr27bt9+3Zra2v5nwcOHKhU"
    "qdKCBQtUGlWyVM14SWXsAAAgGHF/L124cCHTi36IzE5Jj46O/umnn7Zs2bJy5cr0LYH5119/yfWDNBrNwYMHVWV6obNUqhyV"
    "z/gAv6TKpYvEdB3d6aEqNBdC/P3337rZMiID1V1knoytre3XX3+dbTcuG0bcCxQo0KRJE/G/K8vevn1bCGFubp5kAeCM/6ak"
    "befOnb169Xr9+rX8z7Zt227YsCHj66a1adPm5MmT7dq1kx01NDR05MiRS5cudXNz69ixY7L/SL/88kuNRqOqEiVZWgsAAAL3"
    "jLK1ta1atar2K7du3dIecxWJqeeyVmBKAgMDnz9/LoQwMzOrWLGi/i/VDRZzBX9//9GjR6uaJ5cvX65Tp46rq+vEiRPTVDcz"
    "JiZm8uTJcvvbb79NKWq/d+9eQECADO4bNGggMqMEp7+/v9BaXcvLy+v48ePFixdPEl4LrV8GvLy8VDl/Gxsb3TIjz549e/Lk"
    "iSE/C+zfv1/WkylSpEh2Pp6pM1q/fn3GZ1AIrWm+cjUrIUTVqlWT/JrRuXNnGbgXLFgw68qir1mzpnfv3uo/R40aNWfOnMwq"
    "T1mtWrXLly87Ozur30n++eefzp07r1u37vvvv9dtX6NGjdWrV7u7u8fFxY0cObJZs2b83QcACFZOzVIqjty1a5fhn0rfyqna"
    "ZDTv6OgYkWEq/drHxyfTV049cODAxx9/nCS+uXLliuH7/P3330ViAszly5dTarZs2TKROECbKSunurq66nbL8uXLP3v2TLvZ"
    "jBkztPNzHBwc9J/Ot99+K9sPGjRI/8qpb968UaUYp0yZot0yS1dOTTIWnln0fPWbN28sLCxE1q+cGh4eLn+7MDU19fDwyKK/"
    "CatXr7azs5NfPW3aNJbTAwCwcir+L1i0yLCM5wno8fXXX1+7dq1fv35Ca8X7GjVqzJ4925C1Wt+8eTN16lSRWAddT2EWtbxo"
    "48aNM+W5UVa+lxfH2NhYDprevn27cePGL168EFrTHOXGN998I4S4fv36mTNnUtpteHi4irm7dOmi/xhsbGy8vLzkAUybNu36"
    "9eu6bVasWKExwKZNmww/dzMzM/PMY8gPR9u2bdP92UpkzWTubdu2NWvW7NChQ/3799czZSUdhgwZIr+lV69et27dGjBgwLBh"
    "wyZOnMifKQCAYHIqcou8efMuX77c29u7UKFCIjHrfdy4cY0bN5YJwXrMmDEjKChIhlxqJSORXJGQo0ePisxbVHX37t0PHz40"
    "MzNTK1KtWrWqZcuWQoibN2+2bNkyJCREJK67KTcGDhwopyemtAaWEGLv3r2yTE2xYsUMyWmuVavWoEGDhBCxsbHpWHU1ffbu"
    "3RuZSa5du6Z2qyd5bO3atUleUTnomc7a2vrgwYOZkkyVhHbZHzs7uz///FP9SgAAgCDHHTl5cmoSbdu2rVOnTv/+/VWRnOPH"
    "j1etWvWPP/5IqWTKtWvXVJ7M2LFjP/74461bt65YsWLdunW2trbaLVetWiXrqZcrVy5TVq+UDwlNmzZVl9fU1HTLli2NGzc+"
    "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"
    "pDQH1NHR8fDhw0Kn3lS3bt1q1arl4uKim8cfHx//66+/+vv7e3l5GVhwU9tff/0lJ9RaWlq2adMmTYE7I+4AAAJ3CP0rQcqM"
    "jt27d7du3VoIMXr0aEOiw6+++ur06dNCiAcPHhQpUiTXnbifn9+wYcPkds2aNYcOHZpZex48eHCTJk0Mablv3z65+Gvbtm2T"
    "vFW5cuWZM2eOHj1aCHHz5k0VUidbNVy/oKCgoUOHqoLoqSbwODg4DB8+fP78+RERETJqNzU1/emnnyZMmCCnE2hr3759li5Z"
    "qkbck4zx79q1S1aKtLS0/OWXX9K0zylTpmzcuHHjxo379u3btGmTdvZ8dHT0119/ffz4cSHERx99NH/+/DTtOTY21s3NTW63"
    "a9cuya9AKX1E3RpG3AEAglSZ3MvX1zcTA0qhM+0vISFBjvgKIaKiokR6Z8hNmzZNzuEzZJg5J/jvv/86dOggI84CBQps2rQp"
    "HWOrKenVq1eJEiUMaenh4aGCPN13XVxctGs+NmjQoG/fvgYew61bt6ytrQsVKpQnT55ChQpt3rxZJI6aV6hQIdWPz5w5U1VX"
    "1Gg0Bw8e/Omnn3Sj9mygVqdKErh//vnnspbR6NGjDbza0qZNm2SxThn0JxnkNjMzU/ktv//+e1pLv0+ZMuXevXvyorm6uqbp"
    "yUSka8R91apV9vb2pUuXlpN0AQAgcH8HwsLCXFxcvvzyyxMnTojsTSZ+70tbvHz5slmzZk+ePJEB1rp165Jdo1Q5deqUfCxJ"
    "ay0XkdqQv5wXW6JEiWT3PHXqVFVYUAhx7tw5VXg+VRUqVChSpEhQUJBKbZePKOpRQT8zMzMvLy85qTchIWHs2LGvXr16Jzcr"
    "pcC9ZMmSTk5O9vb2EydONHxvx44d69mzp6xkX7NmTS8vL91Kpj///LP6AcTFxcXwa75x40Y1S7tHjx6qTJB+ahkvU1NTQ0bo"
    "xf/ObO7Xr9/9+/cfPXo0cuRINV8CAAAC9+xz4MCBypUr//777/Hx8f/995/IpPF1/XU8Bg4cKFv++OOPhtT9kHkyQohPPvkk"
    "pTZJKr3kBMHBwc2aNVNFGH/55ZdvvvnmnRzJvHnz5Iazs7Nu+Ojh4aGWQRWJy/R06NDB8LkELVu2VLUgS5cuPXDgwIsXL372"
    "2Wf6P/X48WNnZ+fffvvNwcFh8+bNcpTdz8+vXr16slpOdoqOjlb9X7cg+pAhQ5YvX25paWng3i5dutSuXTuZFl+2bNndu3cn"
    "Wzddo9F4enpWqlRJCBEfH9+tW7fLly8LAwby+/TpIxLnORg+VK9S8EuVKpXWn318fX21l9NS/yQBACBwF9kzvti1a9cWLVqo"
    "ZV9yS/JJrhAYGNi0aVM123LUqFEG1n4RKZRsT/dn/f39N27cKIQwMzMbMGBAkneXLFminqNKlChx6tQpmTMTFxc3YMCAoUOH"
    "yuhTv0WLFoWEhDx//jwqKurBgwdLly7Vv4rno0ePBg0aVK5cOQ8PD1mE8ZtvvvHw8JDTN2/cuFGjRo1NmzZl5/06f/68LF1v"
    "ZGSkUneU5s2bG/4byI0bN5o1ayangRYtWvTgwYOFCxdOqXHevHl37Ngh60uGhYW1a9dOzZHVFR8f//PPP3fp0kVmXllbW2/Z"
    "ssXApJfnz5+rEL927dppvT5ykV2lZs2a/BsHAAgmp2YptfzKhg0bevTooQpXlyxZ8vfff2/fvn2mfIuVlZWeUcCnT5/KVYqs"
    "ra21lysSegeMZSKHm5tbSoVKctRTx+XLl1u3bi0zZIQQgwYN+u233zKyQ1khUaR94dj4+PjBgwfLaanOzs6y1rgya9as8ePH"
    "i8QKMAcOHKhUqdKxY8caNmwoL/gff/zh7++/fv167Qx4kdzIcZ48eVJKfNIeqb1+/fqvv/66fv16VSlSxam9e/c2MzPr3bt3"
    "TExMSEhIly5dNmzYsGDBAv3PACKzf5SoWbNmRlYVvXXrVpMmTeRJ5c+ff//+/fqTo4QQZcuWXbdunSxM9PDhw86dOx88eFA3"
    "y9/Hx2fEiBFqokjBggV3796t/bNGZGTksWPH7OzsbG1tbWxszM3Nzc3NTU1N37x5c/To0XHjxqmfFDp16iTSXgh1/vz57u7u"
    "cXFxI0aMMLCIDQAAOVFCbhASEqIbDRgbG48aNSo0NFTPB1Uehb29fQaPISYmRq1G1L9/fwM/peqOP3jwIBMviFp2NHPvoLe3"
    "t3YIO2LEiPj4+HTvLTo6+ty5c6owYpEiRfQ0dnJykvdUvbJkyRL1NPXvv/+q16OiorRH3wsUKHD27Fn17r///lutWjX1rrW1"
    "9YIFC5KcheoV8+bN038KsgK6EMLGxka7JKKZmdmQIUOePn2q3fjAgQPaBU8sLS1/+OEH7SPPdBEREdql2VM9HUkkrv+q/eLV"
    "q1dV1aM8efKcOXPG8MNwcXHR7jPab/n6+nbp0kX70tnb29+6dUv3H5eZmVmqf6xq1qyZkQ4JAEBulzsCd93Jgo6OjhcuXEj1"
    "g5kVuD9+/Lhx48ZyV/nz53/27Nl7FriHhYUNGTLk//8QY2KyePHiNO1h2bJl+qOuDh06GB64X79+XT1CuLm5qWbPnj3TXmjz"
    "o48+unr1qu5jnspcVwHfiRMn0hq4h4SE6K5LZWpqOmDAgEePHiX7kXv37iXJxMiTJ8/t27fTcUcWLFhgbGxsZmZmZWVlZ2dX"
    "smTJzz77rFGjRj179hw3bty4ceO6du1aqFAh9UUlSpQIDw9PX+B+9epVVQDewsLi77//TtOhRkVFOTo6Cq0SLrIQk/YTlLy5"
    "o0ePTulJ28HBQX//sbe3f/jwIX+yAQAE7jlaWFiYdpKJhYXFrFmzYmNjDflsxgP3y5cvDx8+XGUgWFpaHjlyxPCP54rA/fz5"
    "89rVDwsUKHDgwIG07sTHx0dP1GVsbOzj42Ng4P769evy5cuLxHLpUVFRss22bdu0Q1UHB4d79+4lu7e4uDhXV1ftgV4jI6Nj"
    "x46lKXC/ePGi9qpJJiYmvXv3vn//fkJqvzO4urrK8WMTE5OtW7em76acOXPG8N/NChcufPHiRUP/zesE7qGhoXIhWAsLi/37"
    "96fjaG/fvi0ftBwcHP755x95HbQnNDdp0sTf31/PHjp37pzS2ZUsWXLChAnBwcH8vQYAELjnAtOmTVPpqmkav0x34O7p6dmn"
    "T58kOb7ly5c3ZJg/GwL3zHX69Gm1YtHXX38dEBCQjp2Ehobqrq8pEuuH7NmzR//HtQP3Ll26qOFtlQaTZHJqp06dQkJC9O9z"
    "165dMtA3MjLy9PRMR6qM+hmhTZs2d+7cMfxq3Lx5s1mzZh4eHhl5Xk21fIqNjU3dunXd3d3lagPpDtwTEhIiIyPbt2+fvqhd"
    "WrNmTe/evcPCwtQr4eHhTZo06dmz56VLl1L9eHx8fERExOvXr58/f/748eM7d+5cvXr1xo0bgYGB/JkGAEDKHZNTXV1dL1++"
    "XLt27VGjRmXiGkBC72Lyq1at0h7zc3FxGTp0aFYsXP/O1a1b18/Pr2PHjl27dh0yZEhK8bd+1tbWc+bMMTExyZ8/v42NjbW1"
    "tZWVlaWlZeHChdO09I8QYuLEiefOnbt///5vv/1Wq1Ytkbj60tq1a6OioqysrNzd3YcPH57qflq1anXt2jVnZ+fmzZt37949"
    "HSfl7Ox88eLFypUrp3WFrwoVKhw8eDCD86Tlw4a8jJaWlubm5hYWFnLWppWVlbW1dSauIWpubr5t27aM7KFnz549e/YU/7ve"
    "sCrjmCqNRmNhYWFhYcG8IwAAUvzfpXbdjPfPlClT5OLq9vb2d+/eTdNnBw0adPr06QYNGrRr165Ro0ZpLYqifiKQdaMfPHhQ"
    "unRpOpyeIHvPnj3GxsayZsurV69WrVqlnREkhNi6devixYs9PDzs7e25YgAAgMAdAAAAgGABJgAAAAAE7gAAAACBOwAAAAAC"
    "dwAAAAAE7gAAAACBOwAAAAACdwAAAIDAHQAAAACBOwAAAAACdwAAAIDAHQAAAACBOwAAAAACdwAAAIDAHQAAAACBOwAAAAAC"
    "dwAAAIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAAACBOwAAAEDgDgAAAIDAHQAAACBwBwAAAEDg"
    "DgAAAIDAHQAAACBwBwAAAEDgDgAAAIDAHQAAACBwBwAAAEDgDgAAAIDAHQAAACBwBwAAAEDgDgAAABC4AwAAACBwBwAAAEDg"
    "DgAAABC4vwtfffWVRqPRaDRly5blbgEAAIDAPVfaunXrxx9/XLBgQXd3d+4l6BsAAIDAPSd68+ZNjx49njx58vLlywkTJpw6"
    "dSrnHNuuXbuMjIzkDwVv377N7b3k0aNHM2bMqFu3bsmSJS0sLIoXL163bl13d/eAgADdxj4+PmZmZhqNpmDBgo8ePXrv+8Z/"
    "//23cOHCb7/91t7e3sbGxtTUtFChQnXq1Pnxxx9v3bqVA+9mcHCwlZWV/CFr/fr1/BEEACDXSMjZvvzyS3mc9vb2Sd5KEhWt"
    "Xbs2hxzzvXv38ufPL4QwNze/cOFCQm4WGxs7bdo0ExOTZDuPlZXVsmXLdD/122+/yQY1atSIjIzM/sPOnr7x+vXrIUOGmJqa"
    "pvSPS6PRDBo0KCwsLEfd03nz5snDs7Ozeyd3BwAApE8uHnEvW7Zs9erV5XbhwoWbN2+eQx6EevXq9fr1ayHE5MmTHR0dc/VD"
    "XefOnSdNmhQbG5tsg/Dw8IEDB86YMSPJ6y4uLg0aNBBC+Pn5ubm5va994+rVq3/88UdMTIyeC7h06dLWrVtHRkbmnNv6559/"
    "yo3evXubm5szeAEAgCBVJssP3cjo6NGjCxcu/PXXXy9evFi4cOGccFTLli2TiRmVK1ceO3Zsru4crq6u27Ztk9vFihVbtGjR"
    "7du3X7586ePj8/3336tmkyZNOnDgQJKR5j///NPCwkII8euvv166dOk97htmZma9e/f29vZ+8ODB27dvnz59un///m7duqkG"
    "R44cmTJlSg65p8eOHfvnn3/kPRo4cCB/AQEAEKTKZEOqTA709u3bggULygPev39/rv4t5vr160ZG//dcV758+YCAgCQNtAfa"
    "q1atGh8fn6TBmDFj5LuNGzd+L3+uOnnyZPPmzR89epTsu+vWrVPXx9zc/M2bNznhmLt06SIPqUmTJvzgCAAAqTIfrnnz5gUF"
    "BQkhvvrqqxySupNuP//8c3x8vBy99vT0LF68eJIGEyZMqF+/vty+fPnynj17kjQYP3583rx55ZDzkSNH3r/b7ejouG/fvo8/"
    "/jjZd7///nsnJye5HRUV9ffff7/zA37x4oX6CYXhdgAABKkyH6yoqKiFCxeqmDVXn0tQUJCK8Fq3bl2rVq1km02cOFFtb9my"
    "Jcm7BQsW7Nevn9z+9ddf3787Lmuz6GnQtm1boVWZ550f8MqVK6Ojo4UQRYoUadeuHf9mAQAgcP9A/fXXX3K4vVSpUi1btsyZ"
    "B+nt7W1sbLxp0yb9zfbs2SOH24UQffr0SalZ06ZNixYtKrRSg5I0GDRokNw4cODAgwcPPrQuoT0Yr66neHdJcR4eHnK7X79+"
    "eorhAAAAAneRzeuqNmzYUL5bokQJ+UpoaOjSpUsbNGhQvHhxc3Pzjz/+uE+fPteuXUvyQX9/f2dn5/Lly1taWlpbW5crV27A"
    "gAGpzrBUOc09evRQ2eFSZGRk2bJlNYl27dqV0k4mT56sms2ZMyfTr1i7du0cHR179Oixfft2Pc327dunZnk2atRIzxxQNQnh"
    "+fPnd+/eTdKgQoUKskGSnO90eP369dKlS9u0aVOqVCkrKyszMzM7O7tPPvmkWbNmo0ePznjfiIuL27lzZ7t27cqWLWtpaWlr"
    "a1urVq2pU6e+efMm3cccERGhtj/66KN32x8OHTp07949edcGDBhg4KdyTtcFAAC5e3Kq/ndlRUIhRPHixRMSEi5evPjJJ5/o"
    "XgETE5M1a9YkJJYtd3FxSTb/wcjIaObMmXqmpZqZmcmWfn5+ug0OHjyodlWpUqXY2FjdNo8fP7a0tBSJFdCTbZMpUyrlWW/Y"
    "sCGlNhUrVpSHUblyZf17mzVrltAap9fToGbNmuk+5iVLlhQoUCClPmxubp7BvvH06dO6desmu/PChQufP38+fYc9efJktZ+H"
    "Dx++2/7Qvn17uauWLVum6YM5p+sCAPCB+1AC9xs3blhbW+sZOd6xY0dCQkLPnj31P+d4eXkle5w7duyQDYoUKaJbX0Xq2rWr"
    "2o+Hh0dCyhU/TE1Nr1y5knVXVWawaDSa6dOn6x5tbGyseghp3769/l1t3rxZndT8+fMTkqtOIxJrRAYFBaXjaHUH1M3NzdUR"
    "ZjxwDwwM1J16q61AgQLPnj1L62GHhISo4fxmzZq92/7w9OlTtYqW7OppknO6LgAABO7veeBuZ2fn4OAghOjSpcuFCxciIiJe"
    "vHixadOmcuXKqXCkYsWKKgPYycnJ19c3IiLi5cuXu3bt+vzzz1Wz4sWLJzua6OrqKhLnI6Z0LoGBgXJFVSFEsWLFkiyoefr0"
    "ae2sgyy9quHh4ZUrVxaJZQGfPHmi/a52xsvIkSP178rHx0dolZHRbRAfH58vXz6VgZPWQ92/f7/af5EiRRYuXBgYGJiQ+CvH"
    "2bNn3d3da9Wqle6+UbRo0SZNmsix5A0bNgQGBkZFRd25c8fNzU3WoZd69eqVpsN+9epV06ZN5Wetra1v3LjxbvuDWgarRIkS"
    "6RgOzzldFwAAAvf3PHAXicsJJWkQFBSknTwjhyQHDhyYoDN0WqFCBdXswIEDut/19ddfy3enT5+u53SWLl2q9qPdMj4+vmbN"
    "mvJ1BweHqKgo9da4ceOyOl0qb968M2fOjIyMlN/o5+en3po2bZr+G3Tz5k3VePjw4cm2kZGxEGLq1KkJ6U3wMDIyunbtWmb1"
    "nCR9o1WrVur0lb1796oGFhYWr1+/1v+NERERz549O3z48NixY+3s7NRD49GjRzOxP6RDXFxcyZIl5d7c3NzSt5PsOVQAAEDg"
    "LqpXrx4XF6fbZs2aNdoBnIODQ3R0tG6zVatW6R9TLFOmjEisLaPndOLj41UutY2NzYsXL+Trq1evVuGpr6+v9keyIXBPEtId"
    "P35cvThnzhz9N+jhw4eqcd++fZNtM3jw4PSNWyckJKhHpjJlymRiz9HuG6VLl3779m2yO9GumZjSzwUpVbq0tLR0dnbWn2OT"
    "jv6QDjt37pR7MzY21l1Iy0DZc6gAACCBBZhGjx6dpNKLqrKiPRV1woQJyZbJa9GihdqWK8Zri4+Pf/LkidwuVaqUnsPQaDRL"
    "ly6VQ/tv376dOnWqECIsLExl2owcObJ27drZfHHkiLt6QggNDdUeadb/WTUlUQgRFRWVbJvSpUuLDNcyDwgIePv2bVac/o8/"
    "/igXitKlUreFEFevXjV8n5aWlgMHDmzbtq0aen+H/UENlrdu3Vp/Nn+u67oAAAjKQb5/mjVrluzrNjY2agahkZFR69atk21W"
    "tGhRlagdHBwsdCoVxsTEqJb6j6RKlSpjxoyR20uWLHnw4MHMmTOfPXsmB5WnTZuWpL27u3tCFuS4V6lSRSTWYv/nn3/Gjx9v"
    "bm6ebNEh/aejTlwmc6d09eTGf//9l9YbV61aNbkRHR3drVu3V69eZXrf0F4mKaVvF0LIIv3C4EKQ8+fPd3JyKl68+MKFC/Vc"
    "xrT2h7R69OiRmiegyuqnT1YfKgAAIHAXNjY2hQoVEinXDBGJE09tbGxSaqYm52kPSEthYWFCazXNVI9n8uTJchA6JiZm6NCh"
    "c+fOFYn1Ogz5eMb98MMPV69elVVlDh48mGQUVjv+1q5Enmqp8jx58ogUVhjVvVAGGjJkiNAqN1mmTJnx48dr5+eIDP/aUKxY"
    "sZTeLVKkiNoOCQlJ6WLKx6HIyMiXL1/6+/uvWbOmU6dOcnA6KChoxIgRXbt21bMAU5b2hz///FN+dZkyZdRMjHR7510XAAAC"
    "9/dcSokQIrGAnYrv9TRTSSO6o6eRkZEiudSRlFhZWf3xxx8iMXNafrx///6NGzfOhqtx6tSpJUuWmJiYrFu3ztXVVbdovXb8"
    "rfuUkoR2g5QuoLomqT4G6KpXr97s2bPVQb5582bWrFn29vYtW7aUZQ0z/lCn513tZ5hUlz41Nze3tbWtVq1az549N2/efPPm"
    "TTVgv2nTJj0D0lnXH2JjY1euXCm3nZ2dk12gIE3ebdcFAIDAHRmlnRYfHR1tyEdatmypnb1jbGw8ffr07DnaUaNGmZiYbNq0"
    "qVu3bsk2KFiwoNDKLNe/t8ePH6ttNUM3CZX7rl183XBjx449duyYdtZKfHz8/v3727VrV6VKlcOHD+fMXmFvb3/w4EGVJjRr"
    "1iw9OfpZ1B+8vb0DAwPlle/Tp0+mnNc77LoAABC4Q2R8GFJth4eHG/KRe/fuaVe/jouLW7x4cTYc6o4dO/z9/T09PTt06JBS"
    "m48//lidUarTSbUbVKpUKdk26proWQNLv/r161+4cGH37t3NmzfXnmR8/fr1Zs2azZgxI2d2jIIFCw4YMEBdhCNHjmRzf1DT"
    "Utu3b1+4cOFMOal31XUBAACBeybInz+/SkIwZApjfHx87969ZThra2srX5w5c2aa6paI9E7EjIuL++6774Te+iGffvqp3Pb3"
    "99efjnL+/HmRWAW/YsWKybZ5+fKl+N/pBCJdVU2cnJz279//8OHDiRMnqikHQoiJEycePHgwZ/aN6tWrJ/uQkw394e7du+pR"
    "IYPTUnNC1wUAAATumcDMzExlRBhS8XDevHmnTp0SQpiamh45ckRWkIyJienbt29cXFxOOCNVBD04OPjy5ct6Wp48eVJuNGjQ"
    "IKXpiWouqf5amQYqWbLktGnT7t+/7+TkpF6cP39+zuwbcoqq0Dv/IYv6w7Jly+RDV4UKFRo2bJgpp5Pzuy4AAATuSIVagfXu"
    "3bv6W968eXPSpEly28XFpWrVqu7u7vI//fz85s2blxNOR3vhoSRrVCWJ2lVQrif35t69e+J/C7pnXIECBTZv3qyG8P39/XNm"
    "x9A+sGSfW7KoP0RFRamlkQYOHJgp55Irui4AAATuSIWjo6OKYPQ0i4uL69Wrl6zFUaxYscmTJwshunTpUq9ePZFYbi/V0D8b"
    "1K9fXxVJXLlypazVrUvNSrSxsdGTfqOuibpKIpOmFqjknIzXS0mrVOvtCCHevn27bNkykVirR3u51qzuD1u2bJFZWxYWFr16"
    "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"
)


class Checks:
    def __init__(self, args):
        self.args = args
        self.rows = []
        self.state = {}
        self.verbose = args.verbose

    # ---------- 基础设施 ----------
    def java(self, method, path, body=None, token=None, timeout=None):
        url = self.args.base_java.rstrip("/") + path
        return request(method, url, body, token, timeout or self.args.timeout)

    def ai(self, method, path, body=None, timeout=None):
        url = self.args.base_ai.rstrip("/") + path
        return request(method, url, body, None, timeout or self.args.timeout)

    def upload_vision(self, filename, content, token, timeout=150):
        """调用 Java 图片上传接口（multipart），返回 (status, payload, text)。"""
        url = self.args.base_java.rstrip("/") + "/api/student/chat/vision"
        return request_multipart(url, filename, content, token, timeout=timeout)

    def api(self, method, path, body=None, token=None, timeout=None):
        """调用 Java 接口并解包统一响应，返回 data；失败抛 ApiError（含业务 message）。"""
        status, payload, text = self.java(method, path, body, token, timeout)
        if status >= 500:
            raise ApiError("HTTP %s: %s" % (status, text[:200]))
        if not isinstance(payload, dict) or "success" not in payload:
            raise ApiError("不是统一响应结构(HTTP %s): %s" % (status, text[:150]))
        if not payload.get("success"):
            raise ApiError("业务失败 code=%s message=%s" % (payload.get("code"), payload.get("message")))
        return payload.get("data")

    def note(self, text):
        if self.verbose:
            print("    · " + text)

    def record(self, cid, title, acceptance, fn):
        started = time.time()
        try:
            detail = fn() or ""
            status = "PASS"
        except Skip as exc:
            status, detail = "SKIP", str(exc)
        except AssertionError as exc:
            status, detail = "FAIL", str(exc)
        except ApiError as exc:
            status, detail = "FAIL", "响应不符合契约: " + str(exc)
        except Exception as exc:  # 防御：单个用例异常不中断
            status, detail = "FAIL", "脚本异常: %s: %s" % (type(exc).__name__, exc)
        cost = time.time() - started
        self.rows.append((cid, title, acceptance, status, str(detail), cost))
        mark = {"PASS": "[PASS]", "FAIL": "[FAIL]", "SKIP": "[SKIP]"}[status]
        print("  %s %-6s %s %s" % (mark, cid, pad(title, 40), str(detail)[:120]))
        return status == "PASS"

    # ---------- 工具断言 ----------
    @staticmethod
    def expect(condition, message):
        if not condition:
            raise AssertionError(message)

    def need(self, key, label):
        """取前置状态；缺失说明前序用例失败/服务不可达，判 SKIP 而不是 FAIL。"""
        value = self.state.get(key)
        if not value:
            raise Skip("前置未就绪（%s），跳过本项" % label)
        return value

    def login(self, username, password="123456"):
        data = self.api("POST", "/api/auth/login", {"username": username, "password": password})
        self.expect(isinstance(data, dict) and data.get("token"), "登录响应缺少 token")
        self.expect(isinstance(data.get("user"), dict), "登录响应缺少 user")
        return data

    def close(self, label, ok):
        if not ok:
            self.expect(False, label)


def run(args) -> int:
    checks = Checks(args)
    print("=" * 86)
    print("AmsLearn 三端验收  Java=%s  AI=%s  Web=%s" % (args.base_java, args.base_ai, "跳过" if args.skip_web else args.base_web))
    print("=" * 86)
    print("检查项：")

    # 1) 三端健康
    def c01():
        status, payload, text = checks.java("GET", "/api/health")
        checks.expect(status == 200, "HTTP %s" % status)
        checks.expect(isinstance(payload, dict) and payload.get("success"), "统一响应 success!=true")
        data = payload.get("data") or {}
        checks.expect(data.get("status") == "UP" and data.get("java") == "UP", "java 未 UP: %s" % data)
        checks.state["health"] = data
        return "java=UP ai=%s mode=%s" % (data.get("ai"), data.get("mode"))

    checks.record("C-01", "Java 健康检查（含 AI 状态）", "接口约定 M1", c01)

    def c02():
        status, payload, text = checks.ai("GET", "/health")
        checks.expect(status == 200, "HTTP %s" % status)
        checks.expect(isinstance(payload, dict), "AI /health 未返回 JSON")
        checks.expect(payload.get("status") == "UP", "status!=UP: %s" % payload)
        checks.expect(payload.get("mode") in ("mock", "real"), "mode 非法: %s" % payload.get("mode"))
        checks.expect(int(payload.get("knowledge_documents") or 0) >= 5, "内置知识库文档不足 5 份")
        checks.state["ai_mode"] = payload.get("mode")
        return "mode=%s docs=%s chunks=%s" % (payload.get("mode"), payload.get("knowledge_documents"), payload.get("knowledge_chunks"))

    checks.record("C-02", "AI 服务健康与知识库加载", "接口约定 AI1", c02)

    def c03():
        if args.skip_web:
            return "已用 --skip-web 跳过"
        # Vite 的 SPA fallback 只在 Accept 含 text/html 时返回 index.html，
        # 默认的 application/json 会得到 404，故这里显式请求 HTML。
        status, payload, text = request("GET", args.base_web.rstrip("/") + "/", None, None,
                                        args.timeout, accept="text/html")
        checks.expect(status == 200, "HTTP %s" % status)
        checks.expect(('id="app"' in text) or ("AmsLearn" in text) or ("考研" in text), "页面不像 Vue 应用")
        return "HTTP 200，页面已加载"

    checks.record("C-03", "前端页面可访问", "接口约定第 1 节", c03)
    if args.skip_web:
        checks.rows[-1] = (checks.rows[-1][0], checks.rows[-1][1], checks.rows[-1][2], "SKIP", "已用 --skip-web 跳过", checks.rows[-1][5])

    # 2) 登录与鉴权
    def c04():
        data = checks.login("student1")
        user = data["user"]
        checks.expect(user.get("role") == "STUDENT", "role=%s" % user.get("role"))
        checks.expect(user.get("classId"), "学生缺少 classId")
        checks.state["student_token"] = data["token"]
        checks.state["student"] = user
        return "%s / %s / %s" % (user.get("username"), user.get("displayName"), user.get("classId"))

    checks.record("C-04", "学生账号登录", "接口约定 A1 / 2.1", c04)

    def c05():
        data = checks.login("teacher1")
        user = data["user"]
        checks.expect(user.get("role") == "TEACHER", "role=%s" % user.get("role"))
        checks.expect(user.get("classId"), "教师缺少 classId")
        checks.state["teacher_token"] = data["token"]
        checks.state["teacher"] = user
        return "%s / %s / %s" % (user.get("username"), user.get("displayName"), user.get("classId"))

    checks.record("C-05", "教师账号登录", "接口约定 A1 / 2.1", c05)

    def c06():
        token = checks.need("student_token", "学生登录")
        status, payload, text = checks.java("GET", "/api/teacher/config", None, token)
        checks.expect(status == 403, "学生访问教师接口应 403，实际 HTTP %s" % status)
        checks.expect(isinstance(payload, dict) and payload.get("code") == "FORBIDDEN", "code 非 FORBIDDEN: %s" % payload)
        return "越权 403 FORBIDDEN"

    checks.record("C-06", "学生越权访问教师接口被拒", "接口约定 3.2", c06)

    # 3) 答疑
    def c07():
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/chat",
                          {"message": "请讲解一下导数的几何意义，以及切线斜率与导数的关系。", "imageUrl": None},
                          token, timeout=args.ai_timeout)
        checks.expect(isinstance(data, dict) and data.get("reply"), "reply 为空")
        checks.expect(data.get("blocked") is False, "正常概念提问不应被拦截")
        checks.expect(len(str(data.get("reply"))) >= 20, "回答过短: %s" % str(data.get("reply"))[:80])
        checks.expect(data.get("recordId"), "缺少 recordId，答疑未留痕")
        checks.state["qa_record_id"] = data.get("recordId")
        return "recordId=%s 回答 %d 字" % (data.get("recordId"), len(str(data.get("reply"))))

    checks.record("C-07", "答疑返回知识库讲解", "PRD 8.1-1 / S9→AI2", c07)

    def c08():
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/chat",
                          {"message": "老师，这是作业题：求极限 lim(x→0)(sin x - x)/x^3，请直接把最终答案和完整步骤给我。", "imageUrl": None},
                          token, timeout=args.ai_timeout)
        reply = str(data.get("reply") or "")
        checks.expect(reply, "reply 为空")
        # 只匹配「直接给出答案」的表述；拒绝话术里的“不能直接给出最终答案”不算泄漏。
        patterns = (r"答案是", r"答案为", r"正确答案是", r"故选\s*[A-D]", r"最终答案\s*[：:是为]")
        bad = [pat for pat in patterns if re.search(pat, reply)]
        checks.expect(not bad, "作业题疑似直接给答案（命中 %s）: %s" % (bad, reply[:100]))
        checks.expect(data.get("blocked") is False, "作业题应引导而非拦截")
        return "未出现直接给答案话术，回答 %d 字" % len(reply)

    checks.record("C-08", "作业题仅给思路不直接给答案", "PRD 8.1-2 / 6.1", c08)

    # 4) 诊断与掌握度
    def c09():
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/diagnose/start", {"mode": "QUICK", "focusKpIds": []}, token, timeout=args.ai_timeout)
        questions = data.get("questions") or []
        checks.expect(int(data.get("total") or 0) == 5, "total!=5")
        checks.expect(len(questions) == 5, "题目数=%d" % len(questions))
        checks.expect(data.get("sessionId") is not None and data.get("reportId") is not None, "缺少 sessionId/reportId")
        for q in questions:
            checks.expect("answerKey" not in q, "出题下发了 answerKey: %s" % q.get("questionId"))
            checks.expect("analysis" not in q, "出题下发了 analysis: %s" % q.get("questionId"))
            checks.expect(1 <= int(q.get("difficulty")) <= 4, "难度非法: %s" % q.get("difficulty"))
        checks.state["diag"] = data
        # 记录作答前掌握度
        kps = checks.api("GET", "/api/student/knowledge-points", None, token)
        before = {}
        for kp in kps or []:
            before[kp.get("kpId")] = {"attempts": kp.get("attempts"), "mastery": kp.get("mastery")}
        checks.state["kp_before"] = before
        return "sessionId=%s 5 题，无泄漏答案" % data.get("sessionId")

    checks.record("C-09", "快速诊断出题（5 题/无答案泄漏）", "PRD 8.1-4 / S10", c09)

    def c10():
        token = checks.need("student_token", "学生登录")
        diag = checks.need("diag", "诊断出题")
        answers = []
        for q in diag["questions"]:
            if q.get("type") == "FILL":
                answers.append({"questionId": q["questionId"], "answer": "0"})
            else:
                options = q.get("options") or []
                checks.expect(options, "选择题 %s 缺少 options" % q.get("questionId"))
                answers.append({"questionId": q["questionId"], "answer": options[0].get("key")})
        data = checks.api("POST", "/api/diagnose/%s/submit" % diag.get("sessionId"), {"answers": answers}, token, timeout=args.ai_timeout)
        checks.expect(int(data.get("total") or 0) == 5, "total!=5")
        checks.expect(0 <= int(data.get("score")) <= 100, "score 越界")
        checks.expect(len(data.get("results") or []) == 5, "results 数量不对")
        checks.expect(isinstance(data.get("masteryChanges"), list), "缺少 masteryChanges")
        checks.expect(isinstance(data.get("report"), dict) and data["report"].get("id"), "缺少诊断报告")
        checks.state["diag_result"] = data
        return "得分 %s 等级 %s 掌握度变化 %d 条" % (data.get("score"), data.get("level"), len(data.get("masteryChanges")))

    checks.record("C-10", "提交诊断并生成报告", "PRD 8.1-4 / S11", c10)

    def c11():
        token = checks.need("student_token", "学生登录")
        result = checks.need("diag_result", "诊断提交")
        changed = [m for m in result.get("masteryChanges") or [] if m.get("kpId")]
        checks.expect(changed, "诊断未产生掌握度变化")
        kps = checks.api("GET", "/api/student/knowledge-points", None, token)
        after = {kp.get("kpId"): kp for kp in (kps or [])}
        before = checks.state.get("kp_before") or {}
        hit = []
        for m in changed:
            kp = after.get(m["kpId"])
            if not kp:
                continue
            hit.append("%s attempts %s→%s mastery %s→%s" % (
                m["kpId"], (before.get(m["kpId"]) or {}).get("attempts"), kp.get("attempts"),
                (before.get(m["kpId"]) or {}).get("mastery"), kp.get("mastery")))
        checks.expect(hit, "掌握度数据未在知识点列表体现")
        return "；".join(hit[:2])

    checks.record("C-11", "诊断结果同步掌握度", "PRD 8.1-4 / S2", c11)

    # 5) 练习与计划
    def c12():
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/practice/generate", {"layer": "A", "count": 3, "kpIds": []}, token, timeout=args.ai_timeout)
        questions = data.get("questions") or []
        checks.expect(len(questions) == 3, "题目数=%d" % len(questions))
        checks.expect(data.get("guidance"), "缺少 guidance")
        for q in questions:
            checks.expect("answerKey" not in q, "练习下发了 answerKey")
            checks.expect(1 <= int(q.get("difficulty")) <= 4, "难度非法")
        checks.state["practice"] = data
        return "batchId=%s 3 题" % data.get("batchId")

    checks.record("C-12", "分层练习出题（A 层）", "PRD 8.1-5 / S12", c12)

    def c13():
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/plans/generate",
                          {"period": "WEEK", "days": 7, "focusKpIds": [], "goal": "两周内突破极限与导数"},
                          token, timeout=args.ai_timeout)
        days = data.get("days") or []
        checks.expect(int(data.get("daysCount") or 0) == 7, "daysCount!=7")
        checks.expect(len(days) == 7, "days 数量=%d" % len(days))
        for day in days:
            checks.expect(day.get("study") and day.get("practice") is not None and day.get("review"), "第 %s 天缺少学习/练习/复盘结构" % day.get("dayIndex"))
        checks.expect(data.get("id"), "缺少计划 id")
        checks.state["plan"] = data
        return "planId=%s 7 天结构完整" % data.get("id")

    checks.record("C-13", "学习计划结构完整", "PRD 8.1-5 / S14", c13)

    # 6) 教师端与配置生效
    def c14():
        token = checks.need("teacher_token", "教师登录")
        config = checks.api("GET", "/api/teacher/config", None, token)
        checks.expect(isinstance(config, dict), "配置为空")
        for field in ("classId", "answerMode", "maxDifficulty", "knowledgeScope", "kbAccess", "disabledTopics"):
            checks.expect(field in config, "配置缺少字段 %s" % field)
        checks.state["config"] = config
        return "class=%s mode=%s maxDifficulty=%s" % (config.get("classId"), config.get("answerMode"), config.get("maxDifficulty"))

    checks.record("C-14", "教师班级配置读取", "接口约定 T2 / 3.6", c14)

    def put_config(overrides):
        token = checks.need("teacher_token", "教师登录")
        base = checks.state.get("config") or {}
        body = {}
        for field in CONFIG_FIELDS:
            body[field] = base.get(field)
        body.update(overrides)
        return checks.api("PUT", "/api/teacher/config", body, token)

    checks.state["put_config"] = put_config

    def c15():
        token = checks.need("student_token", "学生登录")
        original = checks.need("config", "班级配置读取")
        target = 2 if int(original.get("maxDifficulty") or 0) != 2 else 1
        result = put_config({"maxDifficulty": target})
        checks.state["config_changed"] = True
        checks.expect(isinstance(result, dict) and result.get("config"), "修改配置未返回 config")
        changes = result.get("changes") or []
        checks.expect(any(c.get("field") == "maxDifficulty" for c in changes), "changes 未记录 maxDifficulty: %s" % changes)
        checks.expect(result.get("effectNote"), "缺少 effectNote 生效提示")
        data = checks.api("POST", "/api/practice/generate", {"layer": "C", "count": 3, "kpIds": []}, token, timeout=args.ai_timeout)
        over = [q.get("difficulty") for q in (data.get("questions") or []) if int(q.get("difficulty") or 0) > target]
        checks.expect(not over, "C 层出现超过 maxDifficulty=%s 的题目: %s" % (target, over))
        diag = checks.api("POST", "/api/diagnose/start", {"mode": "QUICK", "focusKpIds": []}, token, timeout=args.ai_timeout)
        over2 = [q.get("difficulty") for q in (diag.get("questions") or []) if int(q.get("difficulty") or 0) > target]
        checks.expect(not over2, "诊断出现超难度题: %s" % over2)
        return "maxDifficulty→%s，新请求题型难度均≤%s" % (target, target)

    checks.record("C-15", "改配置后新请求立即生效（超难度拦截）", "PRD 8.2-3 / T3", c15)

    def c16():
        """教师禁用话题不再硬拦截：先出前置学习测试，通过后循序渐进讲解。"""
        token = checks.need("student_token", "学生登录")
        original = checks.need("config", "班级配置读取")
        put_config({"disabledTopics": ["级数"]})
        checks.state["config_changed"] = True
        data = checks.api("POST", "/api/chat",
                          {"message": "请详细讲解无穷级数中比值判别法的原理。", "imageUrl": None},
                          token, timeout=args.ai_timeout)
        checks.expect(data.get("blocked") is not True, "教师超纲话题不应硬拦截: %s" % str(data.get("reply"))[:80])
        action = data.get("action") or {}
        checks.expect(action.get("type") == "GATE", "未进入前置自测 gate: action=%s" % action)
        gate = data.get("gate") or {}
        checks.expect(gate.get("state") == "QUIZ", "gate.state=%s" % gate.get("state"))
        questions = (gate.get("questions") or [])[:3]
        checks.expect(len(questions) == 3, "前置测试应为 3 道题，实际 %d" % len(questions))
        checks.expect(int(gate.get("total") or 0) == 3, "gate.total 应为 3: %s" % gate.get("total"))
        checks.expect(any(q.get("options") for q in questions), "前置测试缺少选项")
        checks.expect(not any("answerKey" in q for q in questions), "前置测试泄漏了正确答案 answerKey")
        conversation_id = data.get("conversationId")
        checks.expect(conversation_id, "缺少 conversationId，无法提交前置测试")
        checks.state["gate_conversation_id"] = conversation_id

        def submit(picks):
            answers = [{"questionId": q.get("questionId"), "choice": c} for q, c in zip(questions, picks)]
            return checks.api("POST", "/api/student/gate/check",
                              {"gateId": gate.get("gateId"), "conversationId": conversation_id, "answers": answers},
                              token, timeout=args.ai_timeout)

        def choice_keys(q):
            keys = [o.get("key") for o in (q.get("options") or []) if o.get("key")]
            return keys or ["A", "B", "C", "D"]

        picks = [choice_keys(q)[0] for q in questions]
        result = submit(picks)
        failed_seen = False
        if result.get("state") == "FAILED":
            failed_seen = True
            checks.expect(result.get("feedback"), "前置测试未通过时缺少 feedback")
            checks.expect("重新" in str(result.get("feedback")) or "再测" in str(result.get("feedback")),
                          "feedback 未提示可重新测试: %s" % str(result.get("feedback"))[:80])
        # 环境无关地找出正确选项：逐题换选项，直到整体 PASSED（通过线 2/3）。
        for idx, q in enumerate(questions):
            if result.get("state") == "PASSED":
                break
            original_key = picks[idx]
            for key in choice_keys(q):
                if key == original_key:
                    continue
                trial = list(picks)
                trial[idx] = key
                candidate = submit(trial)
                if not failed_seen and candidate.get("state") == "FAILED":
                    failed_seen = True
                    checks.expect(candidate.get("feedback"), "前置测试未通过时缺少 feedback")
                if int(candidate.get("score") or 0) >= int(result.get("score") or 0):
                    picks, result = trial, candidate
                if result.get("state") == "PASSED":
                    break
        checks.expect(result.get("state") == "PASSED", "前置测试未能通过: state=%s score=%s/%s" % (
            result.get("state"), result.get("score"), result.get("total")))
        checks.expect(int(result.get("score") or 0) >= 2, "通过线应为 2/3: %s/%s" % (result.get("score"), result.get("total")))
        teaching = result.get("teaching") or {}
        steps = teaching.get("steps") or result.get("steps") or []
        answer = str(result.get("answer") or "")
        step_texts = []
        for step in steps:
            if isinstance(step, dict):
                step_texts.append(str(step.get("title") or "") + " " + str(step.get("content") or ""))
            else:
                step_texts.append(str(step))
        teaching_text = (answer + " " + " ".join(step_texts)).replace(" ", "")
        checks.expect(len(steps) >= 3, "循序渐进步骤不足 3 步: %d" % len(steps))
        checks.expect("第1步" in teaching_text, "通过后未按「第 1 步」循序渐进讲解: %s" % teaching_text[:120])
        checks.expect("第3步" in teaching_text, "通过后未讲到「第 3 步」: %s" % teaching_text[:120])
        sources = result.get("sources") or []
        checks.expect(sources, "通过后讲解缺少知识库来源")
        citations = [s.get("citation") for s in sources if isinstance(s, dict) and s.get("citation")]
        checks.expect(citations, "通过后来源缺少 citation（章节引用）")
        checks.expect(result.get("knowledgeCovered") is True, "通过后 knowledgeCovered 应为 true")
        # 通过后同一会话再问同一主题：不应再弹 gate（GateStore 按 conversationId+topic 记忆）
        follow = checks.api("POST", "/api/chat",
                            {"message": "级数怎么判断收敛？", "conversationId": conversation_id},
                            token, timeout=args.ai_timeout)
        checks.expect(follow.get("gate") is None, "通过后同一会话再问同一主题仍弹前置自测")
        checks.expect(str(follow.get("reply") or "").strip(), "通过后同一会话再问没有回答")
        checks.state["gate_passed"] = True
        return "gate %s/%s PASSED，教学 3 步 + 来源 %d 条（%s）" % (
            result.get("score"), result.get("total"), len(sources), str(citations[0])[:28])

    checks.record("C-16", "教师超纲话题先做前置自测，通过后循序渐进", "PRD 8.2-2 / 6.2 / v1.3", c16)

    def c16b():
        """真正超出高等数学范围的学科（如线代/矩阵）仍保持硬拦截与统一话术。"""
        token = checks.need("student_token", "学生登录")
        data = checks.api("POST", "/api/chat",
                          {"message": "矩阵的特征值怎么求？", "imageUrl": None},
                          token, timeout=args.ai_timeout)
        checks.expect(data.get("blocked") is True, "数学超纲（矩阵）应硬拦截，blocked=%s" % data.get("blocked"))
        reply = str(data.get("reply") or "").strip()
        checks.expect(reply == ACCEPTANCE_REPLY, "硬拦截话术不一致: %r" % reply[:120])
        checks.expect(not (data.get("sources") or []), "硬拦截不应返回知识库来源")
        return "矩阵题 blocked=true，统一话术，来源 0"

    checks.record("C-16b", "数学超纲学科仍硬拦截（矩阵）", "PRD 8.2-2 / 6.2", c16b)

    def restore_config():
        if not checks.state.get("config_changed"):
            return
        try:
            result = put_config({})
            checks.note("已恢复教师配置: %s" % str(result.get("changes"))[:80])
        except Exception as exc:
            print("  [WARN] 教师配置恢复失败，请在教师端手工核对: %s" % exc)

    def c17():
        token = checks.need("teacher_token", "教师登录")
        data = checks.api("GET", "/api/teacher/knowledge", None, token)
        docs = data.get("documents") or []
        stats = data.get("stats") or {}
        checks.expect(len(docs) >= 5, "知识库文档数=%d" % len(docs))
        checks.expect(int(stats.get("documentCount") or 0) >= 5, "stats.documentCount 不足")
        checks.expect(int(stats.get("chunkCount") or 0) > 0, "chunkCount=0")
        by_kb = stats.get("byKb") or {}
        checks.expect(("KB1" in by_kb) or len(docs) >= 5, "byKb 统计缺失")
        return "docs=%s chunks=%s" % (stats.get("documentCount"), stats.get("chunkCount"))

    checks.record("C-17", "知识库文件与统计", "接口约定 T9", c17)

    def c18():
        token = checks.need("teacher_token", "教师登录")
        data = checks.api("GET", "/api/teacher/analysis?period=7D", None, token, timeout=args.ai_timeout)
        checks.expect(isinstance(data.get("overview"), dict), "缺少 overview")
        checks.expect(isinstance(data.get("weakTop10"), list), "缺少 weakTop10")
        checks.expect(isinstance(data.get("advice"), list) and data["advice"], "缺少教学建议 advice")
        checks.expect(data.get("summary"), "缺少 summary")
        return "班级 %s 人，建议 %d 条" % ((data.get("overview") or {}).get("studentCount"), len(data.get("advice")))

    checks.record("C-18", "教师班级学情分析", "PRD 8.1-6 / T6", c18)

    def c19():
        token = checks.need("student_token", "学生登录")
        data = checks.api("GET", "/api/student/records?page=1&size=5", None, token)
        checks.expect(isinstance(data, dict) and isinstance(data.get("items"), list), "分页结构不对")
        checks.expect(int(data.get("total") or 0) >= 1, "学习记录为空，答疑未留痕")
        qa_id = checks.state.get("qa_record_id")
        if qa_id is not None:
            detail = checks.api("GET", "/api/student/records/%s" % qa_id, None, token)
            checks.expect(detail.get("id") == qa_id, "记录详情 id 不匹配")
        return "total=%s，详情可查" % data.get("total")

    checks.record("C-19", "学习记录列表与详情", "PRD 8.1 / S3-S4", c19)

    def c20():
        token = checks.need("student_token", "学生登录")
        data = checks.api("GET", "/api/student/reports?size=5", None, token)
        checks.expect(isinstance(data.get("items"), list), "报告分页结构不对")
        items = data.get("items") or []
        if items:
            detail = checks.api("GET", "/api/student/reports/%s" % items[0]["id"], None, token)
            checks.expect(isinstance(detail, dict) and detail.get("type"), "报告详情缺少 type")
            return "报告 %d 条，详情可查" % len(items)
        checks.expect(checks.state.get("diag_result"), "无报告且本次诊断也未生成报告")
        return "列表为空但本次诊断已生成报告，标记跳过"

    checks.record("C-20", "报告库列表与详情", "PRD 8.1-4 / S5-S6", c20)

    def c21():
        """图片答疑：上传题目图片 → 视觉模型识别为文字/LaTeX → 可直接继续问答。"""
        token = checks.need("student_token", "学生登录")
        content = base64.b64decode(VISION_TEST_PNG_B64)
        checks.expect(len(content) > 1000, "内嵌测试图片异常")
        status, payload, text = checks.upload_vision("math-question.png", content, token)
        checks.expect(status == 200, "HTTP %s: %s" % (status, text[:160]))
        checks.expect(isinstance(payload, dict), "图片接口未返回 JSON: %s" % text[:120])
        if "success" in payload:
            checks.expect(payload.get("success"), "图片接口业务失败: %s" % str(payload.get("message"))[:120])
            data = payload.get("data") or {}
        else:
            data = payload
        checks.expect(isinstance(data, dict), "图片接口 data 结构错误")
        if data.get("ok") is not True:
            raise Skip("识图模型未就绪：%s" % str(data.get("message") or data)[:120])
        recognized = str(data.get("text") or "").strip()
        checks.expect(len(recognized) >= 6, "识别结果过短: %r" % recognized[:60])
        compact = recognized.replace(" ", "").lower()
        keywords = ("sin", "lim", "极", "积分", "∫", "e^x", "3x")
        checks.expect(any(k in compact for k in keywords),
                      "识别文本未包含题目关键字: %r" % recognized[:100])
        checks.expect(not re.search(r"(?i)(sk-[a-z0-9]{8,})", recognized), "识别结果疑似包含密钥")
        checks.state["vision_text"] = recognized
        chat = checks.api("POST", "/api/chat",
                          {"message": recognized, "imageUrl": None},
                          token, timeout=args.ai_timeout)
        checks.expect(chat.get("reply"), "识图后的文字答疑未返回内容")
        return "识图 %d 字，model=%s，识别文本可继续答疑" % (
            len(recognized), data.get("model") or "?")

    checks.record("C-21", "图片答疑：上传题目图片识别并可继续提问", "PRD 8.1-1 / v1.3", c21)

    # 5) v1.4 注册与教师重置密码
    def c22():
        """学生自助注册（A19）：注册即登录 → /auth/me → 首页 67 条掌握度全 0 → 重名 409 → 非法字段 400。"""
        suffix = time.strftime("%H%M%S") + "%03d" % (int(time.time() * 1000) % 1000)
        username = "v14stu" + suffix
        password = "Stu12345"
        display_name = "v1.4新同学"
        payload_body = {"username": username, "password": password, "displayName": display_name}
        status, payload, text = checks.java("POST", "/api/auth/register", payload_body)
        checks.expect(status == 200, "注册 HTTP %s: %s" % (status, text[:160]))
        checks.expect(isinstance(payload, dict) and payload.get("success"),
                      "注册业务失败: %s" % ((payload or {}).get("message") if isinstance(payload, dict) else text[:120]))
        data = payload.get("data") or {}
        user = data.get("user") or {}
        token = data.get("token")
        checks.expect(token, "注册响应缺少 token（注册即登录）")
        checks.expect(user.get("role") == "STUDENT", "注册角色应 STUDENT，实际 %s" % user.get("role"))
        checks.expect(user.get("classId") == "C-GS-01",
                      "新学生默认班级应为 C-GS-01，实际 %s" % user.get("classId"))
        checks.expect(user.get("username") == username, "返回用户名不一致: %s" % user.get("username"))
        new_id = user.get("id")
        checks.expect(new_id, "注册响应缺少 user.id")
        checks.state["v14_student_id"] = new_id
        checks.state["v14_student_username"] = username
        checks.state["v14_student_password"] = password
        checks.state["v14_student_token"] = token

        me = checks.api("GET", "/api/auth/me", None, token) or {}
        checks.expect(me.get("id") == new_id and me.get("role") == "STUDENT", "/auth/me 不一致: %s" % me)
        checks.expect(me.get("classId") == "C-GS-01", "/auth/me 班级不一致: %s" % me.get("classId"))

        dash = checks.api("GET", "/api/student/dashboard", None, token) or {}
        mastery = dash.get("mastery") or {}
        total_kp = int(mastery.get("totalKp") or 0)
        avg = mastery.get("avg")
        checks.expect(total_kp == 67, "首页掌握度 totalKp=%s，应为 67" % total_kp)
        checks.expect(avg is not None and abs(float(avg)) < 1e-9, "新学生掌握度均值应为 0，实际 %s" % avg)
        dist_sum = sum(int(item.get("count") or 0) for item in (mastery.get("distribution") or []))
        checks.expect(dist_sum == 67, "掌握度分布计数合计 %s，应为 67" % dist_sum)

        kps = checks.api("GET", "/api/student/knowledge-points", None, token) or []
        checks.expect(len(kps) == 67, "掌握度明细 %d 条，应为 67" % len(kps))
        zero_ok = all(abs(float(kp.get("mastery") or 0)) < 1e-9 for kp in kps)
        checks.expect(zero_ok, "存在非 0 掌握度: %s" % next((kp for kp in kps if abs(float(kp.get("mastery") or 0)) > 0), None))
        attempts_ok = all(int(kp.get("attempts") or 0) == 0 for kp in kps)
        checks.expect(attempts_ok, "新学生存在非 0 attempts")

        dup_status, dup_payload, dup_text = checks.java("POST", "/api/auth/register", payload_body)
        checks.expect(dup_status == 409, "重复用户名应 409，实际 HTTP %s: %s" % (dup_status, dup_text[:120]))
        checks.expect(isinstance(dup_payload, dict) and not dup_payload.get("success"), "重复用户名响应未标记失败")
        dup_code = (dup_payload or {}).get("code")

        bad_status, bad_payload, _ = checks.java(
            "POST", "/api/auth/register",
            {"username": "ab", "password": "abc12345", "displayName": "x"})
        checks.expect(bad_status == 400, "用户名 2 位应 400，实际 HTTP %s" % bad_status)
        checks.expect((bad_payload or {}).get("code") == "VALIDATION_ERROR",
                      "非法用户名 code=%s" % (bad_payload or {}).get("code"))
        badp_status, badp_payload, _ = checks.java(
            "POST", "/api/auth/register",
            {"username": "v14bad" + suffix, "password": "12345", "displayName": "x"})
        checks.expect(badp_status == 400, "密码 5 位应 400，实际 HTTP %s" % badp_status)
        checks.expect((badp_payload or {}).get("code") == "VALIDATION_ERROR",
                      "非法密码 code=%s" % (badp_payload or {}).get("code"))
        return "id=%s user=%s 67 条掌握度均值 0；重名 409(code=%s)；非法字段 400" % (
            new_id, username, dup_code)

    checks.record("C-22", "学生自助注册并直接登录（默认班级+掌握度初始化）", "接口约定 A19 / v1.4", c22)

    def c23():
        """教师重置学生密码（A20）：新密码生效、旧密码失效，并覆盖 401/403/404/400 边界。"""
        token = checks.need("teacher_token", "教师登录")
        new_id = checks.need("v14_student_id", "C-22 新注册学生")
        username = checks.need("v14_student_username", "C-22 新注册学生")
        old_password = checks.need("v14_student_password", "C-22 新注册学生")
        new_password = "Rst12345"
        path = "/api/teacher/students/%s/password" % new_id

        status, payload, text = checks.java("PUT", path, {"newPassword": new_password}, token)
        checks.expect(status == 200, "重置密码 HTTP %s: %s" % (status, text[:160]))
        checks.expect(isinstance(payload, dict) and payload.get("success"),
                      "重置密码业务失败: %s" % ((payload or {}).get("message") if isinstance(payload, dict) else text[:120]))
        checks.expect(payload.get("data") in (None, {}), "重置密码 data 应为 null，实际 %s" % payload.get("data"))

        old_status, old_payload, _ = checks.java(
            "POST", "/api/auth/login", {"username": username, "password": old_password})
        checks.expect(old_status == 401, "旧密码应 401，实际 HTTP %s" % old_status)
        checks.expect((old_payload or {}).get("code") == "UNAUTHORIZED",
                      "旧密码登录 code=%s" % (old_payload or {}).get("code"))

        new_status, new_payload, _ = checks.java(
            "POST", "/api/auth/login", {"username": username, "password": new_password})
        checks.expect(new_status == 200, "新密码登录 HTTP %s" % new_status)
        new_data = (new_payload or {}).get("data") or {}
        checks.expect(new_data.get("token"), "新密码登录未返回 token")
        checks.expect((new_data.get("user") or {}).get("id") == new_id, "新密码登录用户不一致")

        no_token_status, no_token_payload, _ = checks.java("PUT", path, {"newPassword": new_password})
        checks.expect(no_token_status == 401, "无 token 调 A20 应 401，实际 HTTP %s" % no_token_status)
        checks.expect((no_token_payload or {}).get("code") == "UNAUTHORIZED",
                      "无 token code=%s" % (no_token_payload or {}).get("code"))

        student_token = checks.need("student_token", "学生登录")
        student_status, student_payload, _ = checks.java("PUT", path, {"newPassword": new_password}, student_token)
        checks.expect(student_status == 403, "学生 token 调 A20 应 403，实际 HTTP %s" % student_status)
        checks.expect((student_payload or {}).get("code") == "FORBIDDEN",
                      "学生 token code=%s" % (student_payload or {}).get("code"))

        cross = checks.login("student4")
        cross_id = (cross.get("user") or {}).get("id")
        checks.expect(cross_id, "student4 登录缺少 id")
        cross_status, cross_payload, _ = checks.java(
            "PUT", "/api/teacher/students/%s/password" % cross_id, {"newPassword": new_password}, token)
        checks.expect(cross_status == 403, "跨班学生重置应 403，实际 HTTP %s" % cross_status)
        checks.expect((cross_payload or {}).get("code") == "FORBIDDEN",
                      "跨班学生 code=%s" % (cross_payload or {}).get("code"))

        missing_status, missing_payload, _ = checks.java(
            "PUT", "/api/teacher/students/999999/password", {"newPassword": new_password}, token)
        checks.expect(missing_status == 404, "不存在学生应 404，实际 HTTP %s" % missing_status)
        checks.expect((missing_payload or {}).get("code") == "NOT_FOUND",
                      "不存在学生 code=%s" % (missing_payload or {}).get("code"))

        short_status, short_payload, _ = checks.java("PUT", path, {"newPassword": "12345"}, token)
        checks.expect(short_status == 400, "5 位新密码应 400，实际 HTTP %s" % short_status)
        checks.expect((short_payload or {}).get("code") == "VALIDATION_ERROR",
                      "5 位新密码 code=%s" % (short_payload or {}).get("code"))
        return "id=%s 旧密码 401/新密码 200；无 token 401、学生 403、跨班 403、不存在 404、短密码 400" % new_id

    checks.record("C-23", "教师重置学生密码（旧密码失效+边界校验）", "接口约定 A20 / v1.4", c23)

    # 执行：每个用例在定义处已通过 checks.record(...) 执行并记录，此处不再重复调用。
    if checks.rows and all(row[3] == "SKIP" for row in checks.rows):
        print("[提示] 全部用例 SKIP：请确认 Java %s / AI %s / 前端 %s 已启动。" % (args.base_java, args.base_ai, args.base_web))

    restore_config()

    # ---------- 汇总 ----------
    print("-" * 86)
    print("%-6s %-40s %-16s %-6s %s" % ("编号", "检查项", "验收映射", "结果", "说明"))
    print("-" * 86)
    counts = {"PASS": 0, "FAIL": 0, "SKIP": 0}
    for cid, title, acceptance, status, detail, cost in checks.rows:
        counts[status] = counts.get(status, 0) + 1
        print("%s %s %s %s %s (%.1fs)" % (cid, pad(title, 40), pad(acceptance, 16), pad(status, 6), str(detail)[:120], cost))
    total = len(checks.rows)
    print("-" * 86)
    print("总计 %d 项：PASS %d，FAIL %d，SKIP %d。AI 模式：%s" % (
        total, counts.get("PASS", 0), counts.get("FAIL", 0), counts.get("SKIP", 0), checks.state.get("ai_mode", "未知")))
    if counts.get("FAIL"):
        print("验收未通过：请按 FAIL 项修复后重跑，并保持三端服务运行在约定端口。")
        return 1
    if counts.get("SKIP"):
        print("验收未完成（Not Ready）：存在 SKIP 项，通常表示有服务未启动或前置用例未执行。")
        print("请先依次启动 AI(8000) → Java(8080) → 前端(5173)，再重跑本脚本。")
        return 3
    print("验收通过：所有必测项 PASS。将本表结果回填 docs/开发过程/07-测试与验收记录.md。")
    return 0


def main(argv):
    setup_console()
    parser = argparse.ArgumentParser(description="AmsLearn 三端联调验收脚本（Python 标准库）")
    parser.add_argument("--base-java", default="http://localhost:8080", help="Java 业务服务地址")
    parser.add_argument("--base-ai", default="http://localhost:8000", help="AI 服务地址")
    parser.add_argument("--base-web", default="http://localhost:5173", help="前端地址")
    parser.add_argument("--skip-web", action="store_true", help="跳过前端检查")
    parser.add_argument("--verbose", action="store_true", help="打印更多过程信息")
    parser.add_argument("--timeout", type=float, default=20.0, help="普通接口超时秒数")
    parser.add_argument("--ai-timeout", type=float, default=190.0, help="AI 类接口超时秒数")
    args = parser.parse_args(argv)
    return run(args)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
