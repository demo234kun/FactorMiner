# -*- coding: utf-8 -*-
"""轮询 run_real_csi300 进度,完成或超时退出。"""
import os, time, re

BASE = r'F:\qlib-dev\FactorMiner'
OUT = os.path.join(BASE, 'run_real_csi300.log')
ERR = os.path.join(BASE, 'run_real_csi300.log.err')


def iter_count():
    n = -1
    for f in (OUT, ERR):
        if not os.path.exists(f):
            continue
        with open(f, encoding='utf-8', errors='replace') as fh:
            for line in fh:
                m = re.search(r'\[ralph\] iter=(\d+)', line)
                if m:
                    n = max(n, int(m.group(1)))
    return n


def has_done():
    for f in (OUT, ERR):
        if os.path.exists(f) and '进化轨迹' in open(f, encoding='utf-8', errors='replace').read():
            return True
    return False


def main():
    start = time.time()
    last = -1
    while time.time() - start < 540:
        ic = iter_count()
        if ic != last:
            print(f'[{time.strftime("%H:%M:%S")}] ralph iter={ic}', flush=True)
            last = ic
        if has_done():
            print('DONE_MARKER', flush=True)
            return
        time.sleep(30)
    print(f'TIMEOUT iter={iter_count()}', flush=True)


if __name__ == '__main__':
    main()
