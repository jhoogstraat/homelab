CREATE EXTENSION IF NOT EXISTS timescaledb;
-- Create the cargo_data table within the schema
CREATE TABLE IF NOT EXISTS cargo_data (
    time TIMESTAMPTZ NOT NULL,
    ship_id TEXT NOT NULL,
    cargo_id TEXT NOT NULL,
    value DOUBLE PRECISION NOT NULL,
    PRIMARY KEY (time, ship_id, cargo_id)
);


SELECT create_hypertable('cargo_data', by_range('time', INTERVAL '1 day'), if_not_exists => TRUE);

-- Create an index to optimize queries on the cargo_data table
CREATE INDEX IF NOT EXISTS idx_ship_cargo_time ON cargo_data (ship_id, cargo_id, time DESC);



-- Set a retention policy to automatically manage old data
SELECT add_retention_policy('cargo_data', INTERVAL '365 days');

-- Enable compression for older data to optimize storage
ALTER TABLE cargo_data SET (
    timescaledb.compress,
    timescaledb.compress_segmentby = 'ship_id',
    timescaledb.compress_orderby = 'time DESC'
);

-- Add a compression policy to compress data after 1 month
SELECT add_compression_policy('cargo_data', INTERVAL '7 days');
