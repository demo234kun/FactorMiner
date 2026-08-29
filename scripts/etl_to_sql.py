# -*- coding: utf-8 -*-
"""
etl_to_sql.py —— 把行情写入本地 Postgres（TimescaleDB）

两种模式：
  --mode synthetic   直接生成合成行情写入本地 SQL（无需 Qlib 数据，用于验证整链）
  --mode qlib        从已下载的 Qlib 原生数据 ETL 到本地 SQL（需先 init_qlib_data.py）

用法（容器内，连 db 服务）：
  python scripts/etl_to_sql.py --mode synthetic --table bars_d --instruments 50
  python scripts/etl_to_sql.py --mode qlib --table bars_d --start 2024-01-01 --end 2025-12-31

环境变量 QLIB_SQL_URI 指向本地库（compose 内默认 postgresql+psycopg2://quant:quant@db:5432/quant）
"""
from __future__ import annotations
import os
import argparse
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text


URI = os.environ.get("QLIB_SQL_URI", "postgresql+psycopg2://quant:quant@db:5432/quant")


def _eng():
    return create_engine(URI)


def synthetic(table: str, n_inst: int, start: str, end: str, freq: str = "1D"):
    eng = _eng()
    insts = [f"SH60{i:04d}" for i in range(1000, 1000 + n_inst)]
    dates = pd.date_range(start, end, freq=freq)
    rows = []
    rng = np.random.default_rng(0)
    for it in insts:
        px = 10 + rng.random() * 20
        for d in dates:
            o = px
            h = px * 1.01
            l = px * 0.99
            c = px * (1 + (rng.random() - 0.5) * 0.03)
            v = rng.random() * 1e6
            a = c * v
            rows.append((d.to_pydatetime(), it, o, h, l, c, v, a))
            px = c
    df = pd.DataFrame(rows, columns=["datetime", "instrument", "open", "high", "low", "close", "volume", "amount"])
    df.to_sql("_stg_bars", eng, if_exists="replace", index=False)
    with eng.begin() as c:
        c.execute(text(
            f"INSERT INTO {table} (datetime,instrument,open,high,low,close,volume,amount) "
            f"SELECT datetime,instrument,open,high,low,close,volume,amount FROM _stg_bars "
            f"ON CONFLICT (instrument, datetime) DO NOTHING; DROP TABLE _stg_bars;"))
    eng.dispose()
    print(f"[etl] synthetic {len(df)} rows -> {table}")


def from_qlib(table: str, start: str, end: str, universe: str = "csi300"):
    import qlib
    from qlib.constant import REG_CN
    from qlib.data import D

    qlib.init(provider_uri=os.environ.get("QLIB_DATA", "/qlib_data/cn_data"), region=REG_CN)
    insts = D.instruments(universe)
    fields = ["$open", "$high", "$low", "$close", "$volume", "$amount"]
    print(f"[etl] 从 Qlib 读取 {universe} {start}~{end} ...")
    df = D.features(insts, fields, start_time=start, end_time=end)
    # df: MultiIndex (datetime, instrument), columns = fields
    df = df.reset_index()
    df.columns = ["datetime", "instrument", "open", "high", "low", "close", "volume", "amount"]
    eng = _eng()
    df.to_sql("_stg_bars", eng, if_exists="replace", index=False)
    with eng.begin() as c:
        c.execute(text(
            f"INSERT INTO {table} (datetime,instrument,open,high,low,close,volume,amount) "
            f"SELECT datetime,instrument,open,high,low,close,volume,amount FROM _stg_bars "
            f"ON CONFLICT (instrument, datetime) DO NOTHING; DROP TABLE _stg_bars;"))
    eng.dispose()
    print(f"[etl] qlib {len(df)} rows -> {table}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["synthetic", "qlib"], default="synthetic")
    ap.add_argument("--table", default="bars_d")
    ap.add_argument("--instruments", type=int, default=50, help="synthetic 模式标的数")
    ap.add_argument("--start", default="2024-01-01")
    ap.add_argument("--end", default="2025-12-31")
    ap.add_argument("--universe", default="csi300")
    args = ap.parse_args()
    if args.mode == "synthetic":
        synthetic(args.table, args.instruments, args.start, args.end)
    else:
        from_qlib(args.table, args.start, args.end, args.universe)


if __name__ == "__main__":
    main()
