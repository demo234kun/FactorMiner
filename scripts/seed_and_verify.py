# -*- coding: utf-8 -*-
"""seed_and_verify.py
尝试用 akshare 拉一只股票的 2024-2026 日线 + 最近分钟真实数据写入本地 Postgres，
随后用 SqlSource 从 Postgres 回读，验证 数据 -> Postgres -> SqlSource -> MarketData
全链路可用。若 akshare 网络被掐，则植入一段“真实形态”的样例数据，仅用于验证链路，
并明确标注为非真实行情。
"""
import os, sys, time, socket
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import numpy as np
import pandas as pd
from sqlalchemy import create_engine, text

URI = "postgresql+psycopg2://quant:quant@localhost:5432/quant"
CODE = "600000"

# --------------------------------------------------------------------------- #
# 写入 Postgres（upsert，幂等）
# --------------------------------------------------------------------------- #
def write_bars(eng, table, rows):
    df = pd.DataFrame(rows, columns=["instrument", "datetime", "open", "high",
                                     "low", "close", "volume", "amount"])
    df.to_sql("_stg", eng, if_exists="replace", index=False)
    with eng.begin() as c:
        c.execute(text(
            f"INSERT INTO {table} (instrument,datetime,open,high,low,close,volume,amount) "
            f"SELECT instrument,datetime,open,high,low,close,volume,amount FROM _stg "
            f"ON CONFLICT (instrument,datetime) DO NOTHING"))
        c.execute(text("DROP TABLE IF EXISTS _stg"))

# --------------------------------------------------------------------------- #
# 尝试真实拉取
# --------------------------------------------------------------------------- #
def try_real():
    socket.setdefaulttimeout(15)
    try:
        import akshare as ak
    except Exception as e:
        print("akshare import ERR", e); return None, None
    daily = minute = None
    for _ in range(2):
        try:
            daily = ak.stock_zh_a_hist(symbol=CODE, period="daily",
                                       start_date="20240101", end_date="20261231",
                                       adjust="qfq")
            if daily is not None and len(daily):
                break
        except Exception as e:
            print("daily fetch ERR", type(e).__name__, str(e)[:70]); time.sleep(1)
    for _ in range(2):
        try:
            minute = ak.stock_zh_a_minute(symbol=CODE, period="1", adjust="")
            if minute is not None and len(minute):
                break
        except Exception as e:
            print("minute fetch ERR", type(e).__name__, str(e)[:70]); time.sleep(1)
    return daily, minute

def real_to_rows(daily, minute):
    drows = []
    if daily is not None and len(daily):
        col = daily.columns
        get = lambda k: daily[col[[c for c in col if k in str(c)][0]]]
        for _, r in daily.iterrows():
            drows.append([
                CODE, pd.to_datetime(str(r["日期"])),
                float(r["开盘"]), float(r["最高"]), float(r["最低"]),
                float(r["收盘"]), float(r["成交量"]), float(r["成交额"]),
            ])
    mrows = []
    if minute is not None and len(minute):
        for _, r in minute.iterrows():
            mrows.append([
                CODE, pd.to_datetime(str(r["day"]) + " " + str(r["time"])),
                float(r["open"]), float(r["high"]), float(r["low"]),
                float(r["close"]), float(r["volume"]), float(r["amount"]),
            ])
    return drows, mrows

# --------------------------------------------------------------------------- #
# 植入真实形态样例（仅在真实拉取失败时使用，明确非真实行情）
# --------------------------------------------------------------------------- #
def plant_rows():
    days = pd.bdate_range("2024-01-02", "2026-12-31")
    rng = np.random.default_rng(1)
    px = 8.0
    drows = []
    for d in days:
        px *= np.exp(rng.standard_normal() * 0.015)
        o = px * (1 + rng.standard_normal() * 0.003)
        h = max(o, px) * (1 + abs(rng.standard_normal()) * 0.004)
        l = min(o, px) * (1 - abs(rng.standard_normal()) * 0.004)
        v = float(np.exp(rng.standard_normal() * 0.5 + 6))
        drows.append([CODE, pd.Timestamp(d), o, h, l, px, v, px * v])
    # 最近 ~3 个交易日分钟
    mdates = pd.bdate_range("2026-08-24", "2026-08-27")
    mrows = []
    for d in mdates:
        for h in range(9, 15):
            for m in range(0, 60, 5):
                if h == 9 and m < 30:
                    continue
                if h == 11 and m > 30:
                    continue
                if h == 15 and m > 0:
                    continue
                t = pd.Timestamp(d).replace(hour=h, minute=m)
                px *= np.exp(rng.standard_normal() * 0.0008)
                o = px * (1 + rng.standard_normal() * 0.0005)
                hh = max(o, px) * (1 + abs(rng.standard_normal()) * 0.0008)
                ll = min(o, px) * (1 - abs(rng.standard_normal()) * 0.0008)
                v = float(np.exp(rng.standard_normal() * 0.4 + 3))
                mrows.append([CODE, t, o, hh, ll, px, v, px * v])
    return drows, mrows

# --------------------------------------------------------------------------- #
# 验证 SqlSource
# --------------------------------------------------------------------------- #
def verify():
    from factorminer.core.data import SqlSource
    from factorminer.core.spec import SqlConfig
    eng = create_engine(URI, pool_pre_ping=True)
    d_cfg = SqlConfig(uri=URI, table="bars_d", instruments=[CODE])
    m_cfg = SqlConfig(uri=URI, table="bars_1m", instruments=[CODE])
    md_d = SqlSource().load(d_cfg, "2024-01-01", "2026-12-31", instruments=[CODE], engine=eng)
    print(f"[verify] bars_d -> MarketData close.shape={md_d.close.shape} "
          f"T={md_d.T} M={md_d.M} sample_close={md_d.close[:3, 0]}")
    md_m = SqlSource().load(m_cfg, "2026-08-01", "2026-12-31", instruments=[CODE], engine=eng)
    print(f"[verify] bars_1m -> MarketData close.shape={md_m.close.shape} sample_close={md_m.close[:3, 0]}")

def main():
    eng = create_engine(URI, pool_pre_ping=True)
    daily, minute = try_real()
    if daily is not None and len(daily):
        drows, mrows = real_to_rows(daily, minute)
        src = "REAL"
    else:
        print("[warn] akshare 真实拉取失败，植入真实形态样例用于链路验证（非真实行情）")
        drows, mrows = plant_rows()
        src = "PLANTED"
    if drows:
        write_bars(eng, "bars_d", drows)
    if mrows:
        write_bars(eng, "bars_1m", mrows)
    with eng.begin() as c:
        nd = c.execute(text("SELECT count(*) FROM bars_d")).scalar()
        nm = c.execute(text("SELECT count(*) FROM bars_1m")).scalar()
    print(f"[seed] source={src} bars_d rows={nd} bars_1m rows={nm}")
    verify()

if __name__ == "__main__":
    main()
