# -*- coding: utf-8 -*-
"""CEMS (cmesdata) -> 本地 Postgres(TimescaleDB) 1 分钟 & 5 分钟行情采集。

数据源：CEMS，提供 a_stock_1min / a_stock_5min，覆盖 2024-2026 真实 A 股。
关键约束：CEMS 单次历史查询**最多 1 年**，故按年分块（2024/2025/2026）。
认证：每次调用传 token_str（从环境变量 CEMS_TOKEN 读取，不落盘）。

并发模型：ThreadPoolExecutor。cmesdata 的 get_historical_data 每次调用是
无状态 HTTP 请求（token 取自参数、内部用 requests.post），线程安全，无需多进程。

用法：
  set CEMS_TOKEN=xxxx
  python collect_cmes.py --limit 2 --freq both        # 抽样验证
  python collect_cmes.py --freq 1min                  # 全 A（沪+深），仅 1 分钟
  python collect_cmes.py --freq both                  # 全 A，1min+5min
  python collect_cmes.py --shard-id 0 --shard-n 8     # 8 片并行（多进程各一片）
"""
from __future__ import annotations
import os
import sys
import time
import random
import argparse
import threading
import pandas as pd
from sqlalchemy import create_engine, text

# 线程池：cmesdata 调用无状态，线程安全；避免 ProcessPool 在 Windows 的 spawn 卡死
from concurrent.futures import ThreadPoolExecutor, as_completed

import psycopg2
from psycopg2.extras import execute_values

URI = os.environ.get("QLIB_SQL_URI", "postgresql+psycopg2://quant:quant@localhost:5432/quant")
YEARS = ("2024", "2025", "2026")
_PG_URI = URI.replace("postgresql+psycopg2://", "postgresql://")
_LOCAL = threading.local()  # 每线程一个 psycopg2 连接


def engine():
    return create_engine(URI, pool_pre_ping=True)


def _conn():
    """每线程复用一个 psycopg2 连接（惰性创建，连接断开则重建）。"""
    c = getattr(_LOCAL, "conn", None)
    if c is None or getattr(c, "closed", 1):
        c = psycopg2.connect(_PG_URI, connect_timeout=30)
        _LOCAL.conn = c
    return c


def cemes_universe() -> list:
    """A 股（沪+深）股票列表，返回 DB 格式（无后缀，如 600000）。

    直接用 CEMS 自身的 symbol 列表作为全集，避免 akshare 列表接口
    （stock_info_sh/sz_name_code）网络重置导致采集卡死。CEMS 返回含北交所，
    这里仅保留 SH./SZ. 以匹配 A 股目标。
    """
    import cmesdata as cs
    tok = os.environ.get("CEMS_TOKEN", "")
    raw = cs.get_symbol_list("a_stock_1min", token_str=tok)
    out = []
    for s in raw:
        if s.startswith(("SH.", "SZ.")):   # 仅沪+深 A 股，排除 BJ 北交所
            out.append(s.split(".", 1)[1])
    return out


def csi_universe() -> list:
    """CSI300/500/1000 成分股合并去重列表（读 csi_universe.json）。"""
    if not os.path.exists(UNIVERSE_JSON):
        raise FileNotFoundError(f"缺少成分股文件: {UNIVERSE_JSON}，先运行 fetch_csi_universe.py")
    import json
    with open(UNIVERSE_JSON, encoding="utf-8") as f:
        return sorted(json.load(f)["union"])


def cmes_sym(code: str) -> str:
    """DB 代码(600000) -> CEMS 符号(SH.600000)。"""
    if code.startswith("6"):
        return "SH." + code
    if code.startswith(("8", "4")):
        return "BJ." + code
    return "SZ." + code


def bulk_insert(table: str, rows: list) -> int:
    """execute_values 批量写入，按 (instrument,datetime) 幂等去重。每线程独立连接。"""
    if not rows:
        return 0
    sql = (f"INSERT INTO {table} (datetime,instrument,open,high,low,close,volume,amount) "
           f"VALUES %s ON CONFLICT (instrument, datetime) DO NOTHING")
    conn = _conn()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows, page_size=30000)
        conn.commit()
    except Exception:
        # 连接可能失效，关闭以便下次重建
        try:
            conn.close()
        except Exception:
            pass
        _LOCAL.conn = None
        raise
    return len(rows)


# 频率 -> (CEMS dataset, 目标表)
FREQ_MAP = {
    "1min": ("a_stock_1min", "bars_1m"),
    "5min": ("a_stock_5min", "bars_5m"),
    "15min": ("a_stock_15min", "bars_15m"),
    "30min": ("a_stock_30min", "bars_30m"),
}

# 可选：指数成分股集合文件(CSI300/500/1000 合并去重)
UNIVERSE_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "csi_universe.json")


def _fetch_one(code: str, sym: str, year: str, freq: str):
    """抓取单只标的单年单频率，返回 (status, n)。status: ok/skip/err。"""
    import cmesdata as cs
    tok = os.environ.get("CEMS_TOKEN", "")
    ds, tbl = FREQ_MAP[freq]
    last = None
    for attempt in range(12):
        try:
            df = cs.get_historical_data(ds, sym, f"{year}-01-01", f"{year}-12-31",
                                        token_str=tok, adjust="adj_none")
            if df is None or len(df) == 0:
                return ("skip", 0)
            # 列名 GBK 编码乱码，按位置取：0=时间 1=开 2=高 3=低 4=收 5=量 6=额
            tcol = df.columns[0]
            # CEMS 源质量问题：最近 9 个交易日(2026-08-17~27)1min 数据重复 240 倍，
            # 按时间戳去重恢复每天 240 行
            if len(df) > len(df[tcol].drop_duplicates()):
                df = df.drop_duplicates(subset=[tcol])
            # 向量化转换：逐行 pd.to_datetime 在 5.8 万行上是灾难(~40s+/任务)，
            # 一次性 to_datetime + to_numpy + zip 构造元组；
            # 注意 numpy 标量必须转 Python 原生 float，否则 execute_values 会
            # 渲染成 np.float64(...) 文本插入 SQL，报 schema "np" does not exist
            dts = pd.to_datetime(df[tcol]).dt.to_pydatetime()
            arr = df.iloc[:, 1:7].to_numpy(dtype=float)
            rows = [(d, code, float(a[0]), float(a[1]), float(a[2]),
                     float(a[3]), float(a[4]), float(a[5]))
                    for d, a in zip(dts, arr)]
            n = bulk_insert(tbl, rows)
            return ("ok", n)
        except Exception as e:  # 含 RateLimitError/网络抖动，指数退避+随机化
            msg = str(e)
            # 确定性错误（退市/停牌股无数据）不重试，直接跳过
            if "没有可获取" in msg or "暂无" in msg or "不存在" in msg or "no data" in msg.lower():
                return ("skip", 0)
            last = e
            wait = min(45, 3 * (attempt + 1)) + random.uniform(0, 2)
            time.sleep(wait)
    return ("err", str(last)[:160])


def _work(task):
    code, sym, year, freq = task
    try:
        st, n = _fetch_one(code, sym, year, freq)
        return (st, code, year, freq, n)
    except Exception as e:  # 兜底，worker 不应崩溃
        return ("err", code, year, freq, str(e)[:160])


def collect(limit=None, freq="both", shard_id=0, shard_n=1, workers=6, universe="all"):
    eng = engine()
    tok_present = bool(os.environ.get("CEMS_TOKEN"))
    print(f"[cmes] token: {'set' if tok_present else 'MISSING'}", flush=True)
    if universe == "csi":
        codes = csi_universe()
        print(f"[cmes] universe(CSI300/500/1000)={len(codes)}", flush=True)
    else:
        codes = cemes_universe()
        print(f"[cmes] universe(A股 SH+SZ)={len(codes)}", flush=True)
    if limit:
        codes = codes[:limit]
    if shard_n > 1:
        codes = [c for i, c in enumerate(codes) if i % shard_n == shard_id]

    if freq == "both":
        freqs = tuple(FREQ_MAP.keys())
    else:
        freqs = (freq,)

    # 断点续传：预取已存在的 (标的, 年) 集合，跳过整年已入库的任务
    present = {}
    for fq, (_, tbl) in FREQ_MAP.items():
        if fq not in freqs:
            continue
        s = set()
        try:
            df = pd.read_sql(
                text(f"SELECT DISTINCT instrument, EXTRACT(YEAR FROM datetime)::int AS yr FROM {tbl}"),
                eng)
            for _, r in df.iterrows():
                s.add((r["instrument"], int(r["yr"])))
        except Exception:
            pass
        present[fq] = s

    tasks = []
    for code in codes:
        sym = cmes_sym(code)
        for yr in YEARS:
            for fq in freqs:
                if (code, int(yr)) in present[fq]:
                    continue
                tasks.append((code, sym, yr, fq))

    print(f"[cmes] shard={shard_id}/{shard_n} freq={freq} tasks={len(tasks)}", flush=True)
    if not tasks:
        print("[cmes] 全部已入库，无需采集", flush=True)
        return

    total = 0
    n_ok = n_skip = n_err = 0
    done = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(_work, t) for t in tasks]
        for fut in as_completed(futs):
            st, code, yr, fq, n = fut.result()
            done += 1
            if st == "ok":
                n_ok += 1; total += (n or 0)
            elif st == "skip":
                n_skip += 1
            else:
                n_err += 1
                print(f"[cmes] ERR {code} {yr} {fq}: {n}", flush=True)
            if done % 25 == 0:
                print(f"[cmes] {done}/{len(tasks)} ok={n_ok} skip={n_skip} err={n_err} rows={total}", flush=True)
    print(f"[cmes] DONE ok={n_ok} skip={n_skip} err={n_err} total_rows={total}", flush=True)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None, help="调试：只采前 N 只")
    ap.add_argument("--freq", choices=["1min", "5min", "15min", "30min", "both"], default="both")
    ap.add_argument("--universe", choices=["all", "csi"], default="all",
                    help="all=全部A股；csi=CSI300/500/1000成分股")
    ap.add_argument("--shard-id", type=int, default=0)
    ap.add_argument("--shard-n", type=int, default=1, help="并行分片总数（多进程各一片）")
    ap.add_argument("--workers", type=int, default=6, help="每片线程内并行数")
    args = ap.parse_args()
    collect(args.limit, args.freq, args.shard_id, args.shard_n, args.workers, args.universe)


if __name__ == "__main__":
    main()
