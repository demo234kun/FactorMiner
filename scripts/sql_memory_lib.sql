-- 四记忆库表结构（Wind 式因子/策略平台）
-- 因子库：挖掘出来的因子与效果
CREATE TABLE IF NOT EXISTS factor_library (
    id          TEXT PRIMARY KEY,
    name        TEXT DEFAULT '',
    formula     TEXT NOT NULL,
    ic          DOUBLE PRECISION DEFAULT 0,
    icir        DOUBLE PRECISION DEFAULT 0,
    max_corr    DOUBLE PRECISION DEFAULT 0,
    source      TEXT DEFAULT 'manual',      -- manual | mining | llm
    note        TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 因子经验库：因子挖掘的经验（推荐方向/禁区/洞察）
CREATE TABLE IF NOT EXISTS factor_experience (
    id          SERIAL PRIMARY KEY,
    kind        TEXT NOT NULL,              -- pattern | forbidden | insight
    content     TEXT NOT NULL,
    detail      TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 策略库：各类策略与回测效果
CREATE TABLE IF NOT EXISTS strategy_library (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    category    TEXT DEFAULT '自定义',
    signal      TEXT NOT NULL,
    direction   TEXT DEFAULT 'long_short',
    description TEXT DEFAULT '',
    -- 回测效果
    sharpe      DOUBLE PRECISION DEFAULT 0,
    annualized  DOUBLE PRECISION DEFAULT 0,
    total_return DOUBLE PRECISION DEFAULT 0,
    max_drawdown DOUBLE PRECISION DEFAULT 0,
    win_rate    DOUBLE PRECISION DEFAULT 0,
    rank_ic     DOUBLE PRECISION DEFAULT 0,
    n_periods   INTEGER DEFAULT 0,
    report_json JSONB DEFAULT '{}',
    created_at  TIMESTAMPTZ DEFAULT now()
);

-- 策略经验库：哪些策略在什么情境下失效/有效
CREATE TABLE IF NOT EXISTS strategy_experience (
    id          TEXT PRIMARY KEY,
    strategy_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    category    TEXT DEFAULT '',
    outcome     TEXT NOT NULL,              -- success | fail
    reason      TEXT DEFAULT '',
    regime      TEXT DEFAULT '',            -- bull | bear | volatile | calm
    sharpe      DOUBLE PRECISION DEFAULT 0,
    market_return DOUBLE PRECISION DEFAULT 0,
    market_vol  DOUBLE PRECISION DEFAULT 0,
    signal      TEXT DEFAULT '',
    created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_fe_kind ON factor_experience(kind);
CREATE INDEX IF NOT EXISTS idx_se_outcome ON strategy_experience(outcome);
CREATE INDEX IF NOT EXISTS idx_se_regime ON strategy_experience(regime);
CREATE INDEX IF NOT EXISTS idx_se_strategy ON strategy_experience(strategy_id);
