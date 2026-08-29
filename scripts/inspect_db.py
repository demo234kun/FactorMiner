# -*- coding: utf-8 -*-
from sqlalchemy import create_engine, text

eng = create_engine("postgresql+psycopg2://quant:quant@localhost:5432/quant", pool_pre_ping=True)
with eng.begin() as c:
    for t in ["bars_d", "bars_1m", "bars_10m"]:
        n = c.execute(text(f"SELECT count(*) FROM {t}")).scalar()
        nd = c.execute(text(f"SELECT count(*) FROM (SELECT DISTINCT instrument, datetime FROM {t}) q")).scalar()
        mn = c.execute(text(f"SELECT min(datetime), max(datetime) FROM {t}")).scalar()
        cons = c.execute(
            text(f"SELECT conname FROM pg_constraint WHERE conrelid='{t}'::regclass AND contype='u'")
        ).fetchall()
        insts = c.execute(text(f"SELECT DISTINCT instrument FROM {t} LIMIT 5")).fetchall()
        print(f"{t}: rows={n} distinct_keys={nd} daterange={mn} "
              f"uniq_cons={[x[0] for x in cons]} insts={[x[0] for x in insts]}")
