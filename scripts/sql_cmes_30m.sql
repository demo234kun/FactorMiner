-- bars_30m: 30 分钟 K 线 hypertable
CREATE TABLE IF NOT EXISTS bars_30m (
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

SELECT create_hypertable('bars_30m', 'datetime', if_not_exists => TRUE);

CREATE INDEX IF NOT EXISTS idx_bars_30m_datetime ON bars_30m (datetime DESC);
CREATE INDEX IF NOT EXISTS idx_bars_30m_instrument ON bars_30m (instrument);

-- 历史灌库期间不压缩
SELECT remove_compression_policy('bars_30m', if_exists => TRUE);
