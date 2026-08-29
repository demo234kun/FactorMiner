# -*- coding: utf-8 -*-
"""akshare -> 本地 Postgres(TimescaleDB) 行情采集。

日线：全 A 2024-2026（新浪 stock_zh_a_daily，可用；东财 stock_zh_a_hist 被网络重置，弃用）。
分钟：新浪 stock_zh_a_minute，仅返回最近约 10 个交易日（2026-08 附近），非 2024 全年历史；
      2024-2026 历史分钟在免费可达源里拿不到（东财历史分钟被掐、新浪只给最近窗口）。

用法：
  python collect_akshare.py --mode daily  --start 2024-01-01 --end 2026-12-31
  python collect_akshare.py --mode minute
  python collect_akshare.py --mode daily  --limit 50        # 抽样验证
  python collect_akshare.py --mode minute --limit 100
"""
from __future__ import annotations
import os
import time
import threading
import argparse
import pandas as pd
from sqlalchemy import create_engine, text

URI = os.environ.get("QLIB_SQL_URI", "postgresql+psycopg2://quant:quant@localhost:5432/quant")


def engine():
    return create_engine(URI, pool_pre_ping=True)


def all_a_codes():
    import akshare as ak
    # 北交所/东财聚合列表接口均被网络重置；用上证+深证列表拼全 A（北交所占比小，暂跳过）
    sh = ak.stock_info_sh_name_code()
    sz = ak.stock_info_sz_name_code()
    codes = list(sh.iloc[:, 0].astype(str)) + list(sz.iloc[:, 0].astype(str))
    return codes


def _sym(code: str) -> str:
    if code.startswith("6"):
        return "sh" + code
    if code.startswith(("8", "4")):
        return "bj" + code
    return "sz" + code


_upsert_lock = threading.Lock()


def upsert(eng, table: str, rows: list) -> int:
    if not rows:
        return 0
    df = pd.DataFrame(rows, columns=["datetime", "instrument", "open", "high", "low", "close", "volume", "amount"])
    with _upsert_lock:
        df.to_sql("_stg", eng, if_exists="replace", index=False)
        with eng.begin() as c:
            c.execute(text(
                f"INSERT INTO {table} (datetime,instrument,open,high,low,close,volume,amount) "
                f"SELECT datetime,instrument,open,high,low,close,volume,amount FROM _stg "
                f"ON CONFLICT (instrument, datetime) DO NOTHING; DROP TABLE _stg;"))
    return len(df)


def collect_daily(start: str, end: str, limit=None, workers=8, per_delay=0.0):
    import akshare as ak
    import socket
    from concurrent.futures import ThreadPoolExecutor, as_completed
    socket.setdefaulttimeout(30)  # 防止东财/新浪个别请求挂起导致整进程卡死
    eng = engine()
    codes = all_a_codes()
    if limit:
        codes = codes[:limit]
    # 断点续传：跳过 bars_d 中已有的标的
    try:
        have = set(pd.read_sql(text("SELECT DISTINCT instrument FROM bars_d"), eng)["instrument"].tolist())
    except Exception:
        have = set()
    pending = [c for c in codes if c not in have]
    print(f"[daily] 全 A={len(codes)} 已入库={len(have)} 待采={len(pending)}")
    s, e = start.replace("-", ""), end.replace("-", "")

    def fetch(code):
        for attempt in range(4):
            try:
                df = ak.stock_zh_a_daily(symbol=_sym(code), start_date=s, end_date=e)
                if df is None or df.empty:
                    return code, []
                rows = [
                    (pd.Timestamp(str(r["date"])).to_pydatetime(), code,
                     float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                     float(r["volume"]), float(r["amount"]))
                    for _, r in df.iterrows()
                ]
                return code, rows
            except Exception as ex:
                if attempt < 3:
                    time.sleep(1.5 * (attempt + 1))
                    continue
                return code, f"{type(ex).__name__}: {str(ex)[:80]}"
        return code, "max-retries"

    total = 0
    n_done = 0
    n_err = 0
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futs = [ex.submit(fetch, c) for c in pending]
        for fut in as_completed(futs):
            code, res = fut.result()
            n_done += 1
            if isinstance(res, list):
                if res:
                    total += upsert(eng, "bars_d", res)
            else:
                n_err += 1
                print(f"[daily] {code} ERR {res}")
            if per_delay:
                time.sleep(per_delay)
            if n_done % 50 == 0:
                print(f"[daily] {n_done}/{len(pending)} rows={total} err={n_err}")
    print(f"[daily] DONE total rows={total} err={n_err}")


def collect_minute(limit=None, delay=0.08):
    import akshare as ak
    import socket
    socket.setdefaulttimeout(30)
    eng = engine()
    codes = all_a_codes()
    if limit:
        codes = codes[:limit]
    total = 0
    for i, code in enumerate(codes):
        if code.startswith(("8", "4")):  # 北交所新浪不提供分钟数据，跳过
            continue
        try:
            df = ak.stock_zh_a_minute(symbol=code, period="1", adjust="")
            if df is None or df.empty:
                continue
            rows = [
                (pd.Timestamp(r["day"]).to_pydatetime(), code,
                 float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]),
                 float(r["volume"]), float(r["amount"]))
                for _, r in df.iterrows()
            ]
            total += upsert(eng, "bars_1m", rows)
        except Exception as ex:
            print(f"[minute] {sym} ERR {type(ex).__name__}: {str(ex)[:80]}")
        if (i + 1) % 20 == 0:
            print(f"[minute] {i + 1}/{len(codes)} rows={total}")
            time.sleep(delay)
    print(f"[minute] DONE total rows={total}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["daily", "minute"], required=True)
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--limit", type=int, default=None, help="调试用：只采前 N 只")
    args = ap.parse_args()
    if args.mode == "daily":
        collect_daily(args.start, args.end, args.limit)
    else:
        collect_minute(args.limit)


if __name__ == "__main__":
    main()
