-- ============================================================
-- FactorMiner CEMS 灌库前准备：关闭 1 分钟/5 分钟表的压缩策略
-- 原因：bars_1m / bars_5m 带有 timescaledb 压缩策略（30 天）。
--       当前日期 2026-08-27，2024/2025/大部分 2026 的 chunk 在灌库期间
--       会被策略压缩，导致后续 INSERT 到已压缩 chunk 失败。
--       表当前为空（0 行），无已压缩 chunk 需 decompress；灌库完成后再按需重建压缩。
-- 应用： python 执行本文件语句（见同目录 apply 逻辑，或 psql -f）
-- ============================================================

-- 1) 移除压缩策略（if_exists 避免表未建策略时报错）
SELECT remove_compression_policy('bars_1m', if_exists => true);
SELECT remove_compression_policy('bars_5m', if_exists => true);

-- 2) 关闭表级压缩开关
ALTER TABLE bars_1m SET (timescaledb.compress = false);
ALTER TABLE bars_5m SET (timescaledb.compress = false);

-- 3) 确认策略已移除（应返回 0 行）
SELECT hypertable_name
FROM timescaledb_information.compression_settings
WHERE hypertable_name IN ('bars_1m', 'bars_5m');
