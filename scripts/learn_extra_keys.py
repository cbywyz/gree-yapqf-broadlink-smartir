#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串行学习 Broadlink remote 的附加红外键（扫风/灯光/睡眠等），带码长截断检测 + 学成回放。

新版 Home Assistant（2024+）的 remote.learn_command 已移除 storage_path 参数，
学到的码自动存入 .storage/broadlink_remote_<mac>_codes。

用法：
  export HASS_URL="http://homeassistant.local:8123"   # 你的 HA 地址
  export HASS_TOKEN="<长期访问令牌>"                   # HA 用户页 -> 安全 -> 长期访问令牌
  python learn_extra_keys.py swing_vertical swing_horizontal

每个键：等待按键(最长60s) -> 读回码校验长度 -> 不合格自动重学 -> 合格则回放一次。
码长阈值 --min-len 默认 600；格力三段式长码完整版约 750+，被截断时常恒定 400。
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.request

try:
    import requests
except ImportError:
    requests = None  # 用 urllib 兜底


def api_call(base, token, path, payload, timeout=90):
    data = json.dumps(payload).encode()
    req = urllib.request.Request(base + path, data=data, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status in (200, 201)
    except Exception as e:
        print("   err:", e, flush=True)
        return False


def read_code_via_ssh(cmd, device, codes_file, ssh_cmd):
    """HA 在远程主机上时，经 SSH 读 storage 文件拿学到的码。本地部署可自行改为直接读文件。"""
    r = subprocess.run(ssh_cmd + ["cat " + codes_file], capture_output=True, text=True, timeout=60)
    out = r.stdout
    i = out.find('{"version"')
    if i < 0:
        return None
    try:
        return json.loads(out[i:out.rfind("}") + 1])["data"][device].get(cmd)
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("commands", nargs="+", help="自定义命令名列表，如 swing_vertical swing_horizontal")
    ap.add_argument("--device", default="gree_extra", help="存储组名（默认 gree_extra）")
    ap.add_argument("--entity", required=True, help="broadlink remote 实体 ID")
    ap.add_argument("--min-len", type=int, default=600, help="合格码最小长度（截断检测）")
    ap.add_argument("--codes-file", default=None, help=".storage/broadlink_remote_<mac>_codes 路径（远程时配合 --ssh）")
    ap.add_argument("--ssh", nargs="+", default=None, help="SSH 命令前缀，如 ssh root@router")
    ap.add_argument("--retries", type=int, default=5, help="每键最大学习次数")
    args = ap.parse_args()

    base = os.environ["HASS_URL"].rstrip("/")
    token = os.environ["HASS_TOKEN"]
    if not args.codes_file:
        sys.exit("需要 --codes-file 指向 /config/.storage/broadlink_remote_<mac>_codes")

    def read_code(cmd):
        if args.ssh:
            return read_code_via_ssh(cmd, args.device, args.codes_file, args.ssh)
        with open(args.codes_file, encoding="utf-8") as f:
            return json.load(f)["data"][args.device].get(cmd)

    for cmd in args.commands:
        old = read_code(cmd)
        ok = False
        for attempt in range(1, args.retries + 1):
            print(f"[{cmd}] 等待按键 (第 {attempt}/{args.retries} 次)…", flush=True)
            if not api_call(base, token, "/api/services/remote/learn_command", {
                "entity_id": args.entity, "device": args.device,
                "command": [cmd], "command_type": "ir", "timeout": 60,
            }):
                continue
            time.sleep(3)
            new = read_code(cmd)
            if new is None or new == old:
                print("   未收到新码", flush=True)
                continue
            if len(new) < args.min_len:
                print(f"   码长 {len(new)} < {args.min_len}，疑似截断，重学", flush=True)
                old = new
                continue
            time.sleep(2)
            api_call(base, token, "/api/services/remote/send_command", {
                "entity_id": args.entity, "device": args.device, "command": [cmd],
            }, timeout=30)
            print(f"   OK 码长 {len(new)}，已回放验证", flush=True)
            ok = True
            break
        if not ok:
            print(f"[{cmd}] 学码失败；若反复得到恒定短码，先确认硬件本身支持该功能", flush=True)


if __name__ == "__main__":
    main()
