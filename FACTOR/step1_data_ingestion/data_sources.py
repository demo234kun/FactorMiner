# -*- coding: utf-8 -*-
"""
data.py —— 数据源层

主数据源为 Qlib（A 股 10 分钟频，CSI500 等指数成分），通过 qlib.data.D.features 读取。
当 qlib 未安装或未初始化数据时，SyntheticSource 提供可运行的合成行情兜底。
"""
from __future__ import annotations
from typing import Optional
import os
import numpy as np
import pandas as pd
from FACTOR.step1_data_ingestion.spec import MarketData, DataConfig, SqlConfig


# --------------------------------------------------------------------------- #
# 合成数据源（兜底，保证端到端可运行）
# --------------------------------------------------------------------------- #
class SyntheticSource:
    """生成带隐含可预测结构的合成 10 分钟行情。"""

    def load(self, cfg: DataConfig) -> MarketData:
        rng = np.random.default_rng(cfg.seed)
        T, M = cfg.n_periods, cfg.n_instruments
        # 每个资产独立随机游走对数收益
        logret = rng.standard_normal((T, M)) * 0.01
        close = np.cumprod(np.exp(logret), axis=0) * 100.0
        open_ = close * (1.0 + rng.standard_normal((T, M)) * 0.001)
        high = np.maximum(open_, close) * (1.0 + np.abs(rng.standard_normal((T, M))) * 0.002)
        low = np.minimum(open_, close) * (1.0 - np.abs(rng.standard_normal((T, M))) * 0.002)
        volume = np.exp(rng.standard_normal((T, M)) * 0.5 + 5.0)
        amt = close * volume
        vwap = (high + low + close) / 3.0
        returns = close / np.roll(close, 1, axis=0) - 1.0
        returns[0] = 0.0

        # 注入 3 个隐含可预测结构（带噪声），使挖掘循环能发现信号
        # 1) 截面反转：当期高 vwap 涨幅 -> 下一期回落
        reversion = vwap / vwap.mean(axis=1, keepdims=True) - 1.0
        # 2) 动量：过去 20 步收益排名
        mom = np.zeros((T, M))
        win = 20
        for t in range(win, T):
            mom[t] = np.argsort(np.argsort(close[t - win:t].mean(axis=0)))
        mom = (mom - mom.mean()) / (mom.std() + 1e-9)
        # 3) 波动聚集：高波动资产下一期收益偏低
        vol = pd.DataFrame(returns).rolling(win).std().fillna(0.0).values.copy()
        vol = np.nan_to_num(vol, 0.0)

        signal = (
            0.6 * (-reversion)        # 反转
            + 0.4 * mom               # 动量
            - 0.3 * vol              # 波动
        )
        noise = rng.standard_normal((T, M)) * 0.9
        # target = 下一根 open-to-close 收益（用信号 + 噪声近似）
        raw = signal + noise
        target = np.roll(raw, -1, axis=0)
        target[-1] = 0.0
        target = target - target.mean(axis=1, keepdims=True)

        times = pd.date_range(cfg.start, periods=T, freq=cfg.freq, tz="UTC")
        instruments = [f"ASSET{i:03d}" for i in range(M)]
        return MarketData(
            times=list(times), instruments=instruments,
            open=open_.astype(float), high=high.astype(float), low=low.astype(float),
            close=close.astype(float), volume=volume.astype(float), amt=amt.astype(float),
            vwap=vwap.astype(float), returns=returns.astype(float), target=target.astype(float),
        )


# --------------------------------------------------------------------------- #
# Qlib 数据源（主）
# --------------------------------------------------------------------------- #
class QlibSource:
    """通过 qlib 读取真实 A 股 10 分钟行情。"""

    @staticmethod
    def available() -> bool:
        try:
            import qlib  # noqa: F401
            return True
        except Exception:
            return False

    def _init(self, provider_uri: Optional[str]):
        import qlib
        from qlib.config import REG_CN
        try:
            if qlib.qlib_init_flag:  # type: ignore
                return
        except Exception:
            pass
        qlib.init(provider_uri=provider_uri, region=REG_CN)

    def load(self, cfg: DataConfig) -> MarketData:
        if not self.available():
            raise RuntimeError(
                "未检测到 qlib。请先 `pip install qlib` 并初始化数据（qlib 的 china data dump）。"
                "或修改 DataConfig.source='synthetic' 使用合成数据。")
        from qlib.data import D

        provider_uri = os.environ.get("QLIB_DATA", None)
        self._init(provider_uri)

        fields = ["$open", "$high", "$low", "$close", "$volume", "$amt"]
        instruments = cfg.instruments if cfg.instruments else cfg.market
        df = D.features(
            instruments, fields,
            start_time=cfg.start, end_time=cfg.end, freq=cfg.freq,
        )
        if df is None or len(df) == 0:
            raise RuntimeError(
                f"Qlib 未取到数据：market={cfg.market} freq={cfg.freq} "
                f"{cfg.start}~{cfg.end}。确认已 dump 对应频率数据。")

        # 整理列名为去掉 $ 前缀，pivot 成 (datetime, instrument) 宽表
        df = df.copy()
        df.columns = [str(c).lstrip("$") for c in df.columns]
        df = df.reset_index()
        df = df.pivot(index=df.columns[0], columns="instrument")
        # 现在 df 是 MultiIndex 列 (field, instrument)
        times = sorted(df.index.unique())
        insts = sorted(df.columns.get_level_values(1).unique())
        T, M = len(times), len(insts)

        def col(name: str) -> np.ndarray:
            arr = df[name].reindex(index=times, columns=insts).values.astype(float)
            return np.nan_to_num(arr, nan=0.0)

        open_ = col("open"); high = col("high"); low = col("low")
        close = col("close"); volume = col("volume"); amt = col("amt")
        vwap = (high + low + close) / 3.0
        returns = close / np.roll(close, 1, axis=0) - 1.0
        returns[0] = 0.0
        # target: 下一根 open-to-close 收益
        target = np.roll(close, -1, axis=0) / close - 1.0
        target[-1] = 0.0

        return MarketData(
            times=list(times), instruments=list(insts),
            open=open_.astype(float), high=high.astype(float), low=low.astype(float),
            close=close.astype(float), volume=volume.astype(float), amt=amt.astype(float),
            vwap=vwap.astype(float), returns=returns.astype(float), target=target.astype(float),
        )


# --------------------------------------------------------------------------- #
# 线上 SQL 数据源（运行时直连，按窗口切片取数，不落本地文件）
# --------------------------------------------------------------------------- #
class SqlSource:
    """运行时直连线上 SQL（如阿里云 RDS PostgreSQL），按 [start,end] × instruments
    切片取数，构造 MarketData。全程只在内存中拼装，不写任何本地数据文件。

    设计要点
    --------
    - 数据库无关：uri 用 SQLAlchemy 连接串（mysql+pymysql://… / postgresql+psycopg2://… /
      clickhouse+clickhouse-sqlalchemy://… 均可），列名通过 SqlConfig 映射。
    - 动态更新友好：线上库持续 INSERT/UPDATE，本类只在程序需要时按窗口查询，
      拿到的永远是最新一段数据。
    - 快速访问：WHERE 命中 (时间范围 + 标的) 索引；limit_per_query 兜底防误拉全量。
    """

    def _engine(self, sql_cfg: SqlConfig, engine=None):
        if engine is not None:
            return engine
        from sqlalchemy import create_engine
        return create_engine(sql_cfg.uri, pool_pre_ping=True)

    def load(self, sql_cfg: SqlConfig, start: str, end: str,
             instruments: Optional[list] = None, engine=None) -> MarketData:
        import numpy as np
        import pandas as pd
        from sqlalchemy import text

        eng = self._engine(sql_cfg, engine)
        insts = instruments if instruments is not None else sql_cfg.instruments
        cols = [sql_cfg.col_instrument, sql_cfg.col_time, sql_cfg.col_open,
                sql_cfg.col_high, sql_cfg.col_low, sql_cfg.col_close,
                sql_cfg.col_volume, sql_cfg.col_amount]
        sel = ", ".join(cols)
        sql = (f"SELECT {sel} FROM {sql_cfg.table} "
               f"WHERE {sql_cfg.col_time} >= :s AND {sql_cfg.col_time} <= :e")
        params = {"s": start, "e": end}
        if insts:
            ph = ", ".join(f":i{k}" for k in range(len(insts)))
            sql += f" AND {sql_cfg.col_instrument} IN ({ph})"
            for k, v in enumerate(insts):
                params[f"i{k}"] = v
        sql += (f" ORDER BY {sql_cfg.col_time}, {sql_cfg.col_instrument} "
                f"LIMIT {int(sql_cfg.limit_per_query)}")

        df = pd.read_sql(text(sql), eng, params=params)
        if df.empty:
            raise RuntimeError(
                f"SQL 查询无数据: table={sql_cfg.table} "
                f"[{start},{end}] insts={insts}")

        tcol, icol = sql_cfg.col_time, sql_cfg.col_instrument
        df[tcol] = df[tcol].astype(str)
        df = df.sort_values([tcol, icol])
        times = list(dict.fromkeys(df[tcol]))
        insts_out = list(dict.fromkeys(df[icol]))
        T, M = len(times), len(insts_out)

        def grid(col: str) -> "np.ndarray":
            p = df.pivot_table(index=tcol, columns=icol, values=col, aggfunc="last")
            p = p.reindex(index=times, columns=insts_out)
            return np.nan_to_num(p.to_numpy(dtype=float), 0.0)

        open_ = grid(sql_cfg.col_open)
        high = grid(sql_cfg.col_high)
        low = grid(sql_cfg.col_low)
        close = grid(sql_cfg.col_close)
        volume = grid(sql_cfg.col_volume)
        amt = grid(sql_cfg.col_amount)
        vwap = (high + low + close) / 3.0
        returns = close / np.roll(close, 1, axis=0) - 1.0
        returns[0] = 0.0
        target = np.roll(close, -1, axis=0) / close - 1.0
        target[-1] = 0.0
        return MarketData(times=times, instruments=insts_out,
                          open=open_, high=high, low=low, close=close,
                          volume=volume, amt=amt, vwap=vwap,
                          returns=returns, target=target)


# --------------------------------------------------------------------------- #
# 工厂
# --------------------------------------------------------------------------- #
def get_data_source(cfg: DataConfig):
    if cfg.source == "qlib":
        return QlibSource()
    return SyntheticSource()
