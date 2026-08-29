-- ============================================================
-- FactorMiner 本地 SQL Schema（本地 PostgreSQL + TimescaleDB）
-- 场景：全 A≈5000 × 日/10min/1min × 2024-2025，偏历史回测扫描，日频动态更新
-- 连接串示例：postgresql+psycopg2://quant:quant@db:5432/quant
-- 应用： python scripts/sql_setup.py --uri <uri> --apply-schema
-- ============================================================

CREATE EXTENSION IF NOT EXISTS timescaledb;

-- 1) 原始行情超表：按频率分表，chunk 按时间切
DROP TABLE IF EXISTS bars_1m CASCADE;
CREATE TABLE bars_1m (
    datetime   TIMESTAMPTZ NOT NULL,
    instrument TEXT         NOT NULL,
    open       DOUBLE PRECISION NOT NULL,
    high       DOUBLE PRECISION NOT NULL,
    low        DOUBLE PRECISION NOT NULL,
    close      DOUBLE PRECISION NOT NULL,
    volume     DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount     DOUBLE PRECISION NOT NULL DEFAULT 0
);
SELECT create_hypertable('bars_1m', 'datetime', chunk_time_interval => INTERVAL '7 day');
CREATE UNIQUE INDEX uq_bars_1m_inst_dt ON bars_1m (instrument, datetime);

DROP TABLE IF EXISTS bars_10m CASCADE;
CREATE TABLE bars_10m (
    datetime   TIMESTAMPTZ NOT NULL,
    instrument TEXT         NOT NULL,
    open       DOUBLE PRECISION NOT NULL,
    high       DOUBLE PRECISION NOT NULL,
    low        DOUBLE PRECISION NOT NULL,
    close      DOUBLE PRECISION NOT NULL,
    volume     DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount     DOUBLE PRECISION NOT NULL DEFAULT 0
);
SELECT create_hypertable('bars_10m', 'datetime', chunk_time_interval => INTERVAL '30 day');
CREATE UNIQUE INDEX uq_bars_10m_inst_dt ON bars_10m (instrument, datetime);

DROP TABLE IF EXISTS bars_d CASCADE;
CREATE TABLE bars_d (
    datetime   TIMESTAMPTZ NOT NULL,
    instrument TEXT         NOT NULL,
    open       DOUBLE PRECISION NOT NULL,
    high       DOUBLE PRECISION NOT NULL,
    low        DOUBLE PRECISION NOT NULL,
    close      DOUBLE PRECISION NOT NULL,
    volume     DOUBLE PRECISION NOT NULL DEFAULT 0,
    amount     DOUBLE PRECISION NOT NULL DEFAULT 0
);
SELECT create_hypertable('bars_d', 'datetime', chunk_time_interval => INTERVAL '90 day');
CREATE UNIQUE INDEX uq_bars_d_inst_dt ON bars_d (instrument, datetime);

-- 2) 连续聚合：1min 按日预聚合成日频，回测日频策略直接扫小表
CREATE MATERIALIZED VIEW bars_daily_cagg
WITH (timescaledb.continuous) AS
SELECT
    instrument,
    time_bucket('1 day', datetime) AS day,
    first(open,  datetime) AS open,
    max(high)            AS high,
    min(low)             AS low,
    last(close, datetime) AS close,
    sum(volume)          AS volume,
    sum(amount)          AS amount
FROM bars_1m
GROUP BY instrument, time_bucket('1 day', datetime)
WITH NO DATA;
CREATE INDEX ix_cagg_inst_day ON bars_daily_cagg (instrument, day);
SELECT add_continuous_aggregate_policy('bars_daily_cagg',
    start_offset   => INTERVAL '3 day',
    end_offset     => INTERVAL '0 day',
    schedule_interval => INTERVAL '1 day');

-- 3) 因子信号表：FactorMiner 计算出的因子值动态写回，按 (instrument, factor_id, datetime) 更新
DROP TABLE IF EXISTS factor_signals CASCADE;
CREATE TABLE factor_signals (
    datetime   TIMESTAMPTZ NOT NULL,
    instrument TEXT         NOT NULL,
    factor_id  TEXT         NOT NULL,
    value      DOUBLE PRECISION NOT NULL
);
SELECT create_hypertable('factor_signals', 'datetime', chunk_time_interval => INTERVAL '30 day');
CREATE UNIQUE INDEX uq_factor_inst_fid_dt ON factor_signals (instrument, factor_id, datetime);
CREATE INDEX ix_factor_fid_dt ON factor_signals (factor_id, datetime);

-- 4) 策略记忆持久化（让 run_pipeline 记忆直接落库）
DROP TABLE IF EXISTS strategy_memory CASCADE;
CREATE TABLE strategy_memory (
    key   TEXT PRIMARY KEY,
    value JSONB NOT NULL
);

-- 5) 压缩策略：历史 chunk 列压缩，降低本地存储成本（1min 表尤其明显）
ALTER TABLE bars_1m SET (timescaledb.compress, timescaledb.compress_segmentby = 'instrument');
SELECT add_compression_policy('bars_1m', INTERVAL '30 day');
ALTER TABLE bars_10m SET (timescaledb.compress, timescaledb.compress_segmentby = 'instrument');
SELECT add_compression_policy('bars_10m', INTERVAL '90 day');
