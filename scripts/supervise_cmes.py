# -*- coding: utf-8 -*-
"""CEMS 采集主管进程：统一托管 3 个分片子进程，异常退出自动重启，全部完成后退出。

用法：
  $env:CEMS_TOKEN = '...'
  python -u scripts/supervise_cmes.py [--workers 2] [--interval 60]

与直接启动 3 个分片相比：
  - 单进程托管，子进程死亡（网络卡死/崩溃）自动按断点续传拉起
  - 全部 shard 日志出现 DONE 后主管退出
  - token 仅存在于本进程环境变量，子进程继承，不落盘
"""
import os
import sys
import time
import argparse
import subprocess

PY = r"F:\Python\python.exe"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # FactorMiner/
SCRIPT = os.path.join(ROOT, "scripts", "collect_cmes.py")


def log(msg: str):
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line, flush=True)
    with open(os.path.join(ROOT, "cmes_supervisor.log"), "a", encoding="utf-8") as f:
        f.write(line + "\n")


def shard_done(i: int) -> bool:
    p = os.path.join(ROOT, f"cmes_shard{i}.log")
    if not os.path.exists(p):
        return False
    try:
        with open(p, encoding="utf-8", errors="replace") as f:
            return "[cmes] DONE" in f.read()
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--shard-n", type=int, default=3)
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--interval", type=int, default=60, help="监控间隔秒")
    args = ap.parse_args()

    tok = os.environ.get("CEMS_TOKEN", "")
    if not tok:
        log("ERROR: CEMS_TOKEN empty, abort")
        sys.exit(1)
    log(f"supervisor start shard_n={args.shard_n} workers={args.workers} interval={args.interval}s")

    procs: dict[int, subprocess.Popen] = {}
    while True:
        # 1) 完成检测：全部 shard DONE
        if all(shard_done(i) for i in range(args.shard_n)):
            log("all shards DONE, supervisor exit")
            break

        # 2) 拉起 / 重启
        for i in range(args.shard_n):
            p = procs.get(i)
            if p is not None and p.poll() is None:
                continue  # 存活
            if shard_done(i):
                continue  # 已完成
            if p is not None:  # 已退出且未完成 -> 重启
                log(f"shard {i} died rc={p.returncode}, relaunch")
            out = open(os.path.join(ROOT, f"cmes_shard{i}.log"), "w", encoding="utf-8")
            err = open(os.path.join(ROOT, f"cmes_shard{i}.log.err"), "w", encoding="utf-8")
            procs[i] = subprocess.Popen(
                [PY, "-u", SCRIPT, "--freq", "both",
                 "--shard-id", str(i), "--shard-n", str(args.shard_n),
                 "--workers", str(args.workers)],
                cwd=ROOT, stdout=out, stderr=err,
                env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            )
            log(f"shard {i} launched pid={procs[i].pid}")

        time.sleep(args.interval)

    for p in procs.values():
        try:
            p.wait(timeout=10)
        except Exception:
            pass
    log("supervisor exit")


if __name__ == "__main__":
    main()
