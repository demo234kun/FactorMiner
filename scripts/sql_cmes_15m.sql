-- bars_15m: 15 分钟 K 线 hypertable,与 bars_d 同构,主键 (instrument, datetime)
CREATE TABLE IF NOT EXISTS bars_15m (
    instrument  VARCHAR(16)  NOT NULL,
    datetime    TIMESTAMPTZ  NOT NULL,
    open        DOUBLE PRECISION,
    high        DOUBLE PRECISION,
    low         DOUBLE PRECISION,
    close       DOUBLE PRECISION,
    volume      DOUBLE PRECISION,
    amount      DOUBLE PRECISION,
    PRIMARY KEY (instrument, datetime)
);

SELECT create_hypertable('bars_15m', 'datetime', if_not_exists => TRUE);

-- 与 bars_d 一致的索引
CREATE INDEX IF NOT EXISTS idx_bars_15m_datetime ON bars_15m (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_bars_15m_instrument ON bars_15m (instrument);

-- 确保无压缩策略(历史灌库期间不压缩)
SELECT remove_compression_policy('bars_15m', if_exists => TRUE);
