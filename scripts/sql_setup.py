# -*- coding: utf-8 -*-
"""
sql_setup.py —— 阿里云 RDS PostgreSQL + TimescaleDB 的初始化与 ETL 工具

职责：
  1) apply_schema(uri, sql_path)   执行 scripts/sql_schema.sql 建表/超表/连续聚合（幂等）
  2) bulk_load_csv(uri, table, csv) 初始历史灌入（2024-2025），用 COPY 高效批量写
  3) upsert_daily_bars(uri, table, df) 日频动态更新：按 (instrument, datetime) 冲突则覆盖

依赖：pip install SQLAlchemy psycopg2-binary pandas
连接串示例：postgresql+psycopg2://user:pass@rm-xxxx.mysql.rds.aliyuncs.com:5432/quant

注意：脚本本身不落任何本地数据文件，仅把数据写入线上 RDS。
"""
from __future__ import annotations
import argparse
import os
from typing import Optional

from sqlalchemy import create_engine, text


def apply_schema(uri: str, sql_path: Optional[str] = None) -> None:
    """执行建表 DDL（幂等：表已存在会 CASCADE 重建，首次运行即建好）。"""
    sql_path = sql_path or os.path.join(os.path.dirname(__file__), "sql_schema.sql")
    with open(sql_path, "r", encoding="utf-8") as f:
        sql = f.read()
    eng = create_engine(uri)
    # 分语句执行（TimescaleDB 过程性语句需逐条）
    for stmt in _split_statements(sql):
        if stmt.strip():
            eng.execute(text(stmt))
    eng.dispose()
    print(f"schema applied from {sql_path}")


def bulk_load_csv(uri: str, table: str, csv_path: str) -> None:
    """初始历史灌入：用 psycopg2 COPY 把 CSV（列: datetime,instrument,open,high,low,close,volume,amount）写入超表。"""
    import psycopg2
    from urllib.parse import urlparse
    # 从 SQLAlchemy URI 解析出 psycopg2 原生 DSN
    u = urlparse(uri)
    # 形如 postgresql+psycopg2://user:pass@host:5432/db
    netloc = u.netloc
    if "@" in netloc:
        cred, host = netloc.split("@", 1)
    else:
        cred, host = "", netloc
    user = cred.split(":")[0] if cred else None
    pwd = cred.split(":")[1] if ":" in cred else None
    db = u.path.lstrip("/")
    conn = psycopg2.connect(host=host, user=user, password=pwd, dbname=db)
    with conn, open(csv_path, "r", encoding="utf-8") as f, conn.cursor() as cur:
        cur.copy_expert(
            f"COPY {table} (datetime,instrument,open,high,low,close,volume,amount) "
            f"FROM STDIN WITH (FORMAT csv, HEADER true)", f)
    conn.close()
    print(f"bulk loaded {csv_path} -> {table}")


def upsert_daily_bars(uri: str, table: str, df) -> None:
    """日频动态更新：把当日各频率行情 DataFrame 按 (instrument, datetime) upsert 进超表。"""
    eng = create_engine(uri)
    # 临时表 + 冲突覆盖，避免重复写入；也支持「修补/重算当日」
    cols = ["datetime", "instrument", "open", "high", "low", "close", "volume", "amount"]
    df = df[cols]
    df.to_sql("_stg_bars", eng, if_exists="replace", index=False)
    with eng.begin() as c:
        c.execute(text(f"""
            INSERT INTO {table} (datetime,instrument,open,high,low,close,volume,amount)
            SELECT datetime,instrument,open,high,low,close,volume,amount FROM _stg_bars
            ON CONFLICT (instrument, datetime) DO UPDATE
               SET open=EXCLUDED.open, high=EXCLUDED.high, low=EXCLUDED.low,
                   close=EXCLUDED.close, volume=EXCLUDED.volume, amount=EXCLUDED.amount;
            DROP TABLE IF EXISTS _stg_bars;
        """))
    eng.dispose()
    print(f"upserted {len(df)} rows -> {table}")


def _split_statements(sql: str):
    """按分号切分，但忽略函数/字符串内的分号（粗略处理，足够本 DDL 使用）。"""
    out, buf = [], []
    for line in sql.splitlines():
        if line.strip().startswith("--"):
            continue
        buf.append(line)
        if line.strip().endswith(";"):
            out.append("\n".join(buf))
            buf = []
    if buf:
        out.append("\n".join(buf))
    return out


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--uri", required=True, help="RDS PostgreSQL 连接串")
    ap.add_argument("--apply-schema", action="store_true", help="执行建表 DDL")
    ap.add_argument("--bulk-csv", help="初始灌入 CSV 路径")
    ap.add_argument("--table", default="bars_1m", help="目标表名")
    args = ap.parse_args()
    if args.apply_schema:
        apply_schema(args.uri)
    if args.bulk_csv:
        bulk_load_csv(args.uri, args.table, args.bulk_csv)
