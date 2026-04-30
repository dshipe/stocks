-- ============================================================
-- db_setup.sql — Database schema for stock scanning system
-- Target: SQL Server (ec2-35-172-202-150.compute-1.amazonaws.com)
-- Database: python
--
-- Run this once before starting the scanners.
-- Safe to re-run: uses IF NOT EXISTS checks throughout.
-- ============================================================

USE [python];
GO

-- ─── watchlist_entries ─────────────────────────────────────────────────────
-- One row per stock per day that meets Stages 1-4 criteria and is
-- within 5% of its pivot (breakout level).

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[watchlist_entries]')
    AND type IN (N'U')
)
BEGIN
    CREATE TABLE [dbo].[watchlist_entries] (
        id                          INT IDENTITY(1,1) PRIMARY KEY,
        scan_date                   DATE NOT NULL,
        ticker                      VARCHAR(10) NOT NULL,
        company_name                VARCHAR(100) NULL,
        price_at_scan               DECIMAL(10,4) NULL,
        pivot_price                 DECIMAL(10,4) NULL,    -- top of consolidation base
        pct_from_pivot              DECIMAL(5,2)  NULL,    -- how far price is from pivot

        -- Stage 2: Prior explosive move
        prior_move_pct              DECIMAL(5,2)  NULL,    -- e.g. 45.3 (%)
        prior_move_days             INT           NULL,    -- days the move took
        
        -- Stage 3: Base metrics
        base_depth_pct              DECIMAL(5,2)  NULL,    -- (base_high - base_low) / base_high * 100
        base_duration_days          INT           NULL,    -- trading days in base

        -- Stage 4: Volume contraction
        volume_contraction_ratio    DECIMAL(5,3)  NULL,    -- base avg vol / 50d avg vol (e.g. 0.42)
        volume_contraction_days     INT           NULL,    -- consecutive below-avg vol days

        -- Stage 1: Universe metrics
        adr_pct                     DECIMAL(5,2)  NULL,    -- average daily range %
        avg_daily_volume            BIGINT        NULL,    -- 20-day avg daily volume

        -- MA alignment flags (Stage 3 R15/R16)
        ma10_above_ma20             BIT           NULL,
        above_50d_ma                BIT           NULL,
        distance_to_pivot_pct       DECIMAL(5,2)  NULL,

        -- Pattern identification
        pattern_type                VARCHAR(20)   NULL,    -- 'VCP', 'HTF', 'FlatBase', 'Pennant'
        pattern_grade               VARCHAR(2)    NULL,    -- 'A+', 'A', 'B', 'C'

        -- Exact qualifying reasons (JSON array of strings)
        qualification_reasons       NVARCHAR(MAX) NULL,

        created_at                  DATETIME DEFAULT GETDATE()
    );

    PRINT 'Created table: watchlist_entries';
END
ELSE
    PRINT 'Table already exists: watchlist_entries';
GO

-- ─── watchlist_performance ─────────────────────────────────────────────────
-- Tracks price performance after each watchlist entry.
-- Filled in daily by performance_tracker.py.

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[watchlist_performance]')
    AND type IN (N'U')
)
BEGIN
    CREATE TABLE [dbo].[watchlist_performance] (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        watchlist_id        INT NOT NULL,
        ticker              VARCHAR(10) NULL,
        scan_date           DATE NULL,

        -- Price snapshots (closing price N trading days after scan_date)
        price_1d            DECIMAL(10,4) NULL,
        price_3d            DECIMAL(10,4) NULL,
        price_5d            DECIMAL(10,4) NULL,
        price_10d           DECIMAL(10,4) NULL,
        price_20d           DECIMAL(10,4) NULL,
        price_60d           DECIMAL(10,4) NULL,

        -- % change from price_at_scan
        pct_change_1d       DECIMAL(6,2)  NULL,
        pct_change_5d       DECIMAL(6,2)  NULL,
        pct_change_10d      DECIMAL(6,2)  NULL,
        pct_change_20d      DECIMAL(6,2)  NULL,
        pct_change_60d      DECIMAL(6,2)  NULL,

        -- Outcome flags
        did_break_out       BIT           NULL,    -- did price exceed pivot within 5 days?
        max_gain_pct        DECIMAL(6,2)  NULL,    -- max gain achieved within 20 trading days
        max_gain_date       DATE          NULL,

        updated_at          DATETIME DEFAULT GETDATE(),

        CONSTRAINT FK_watchlist_performance_entry
            FOREIGN KEY (watchlist_id) REFERENCES watchlist_entries(id)
    );

    PRINT 'Created table: watchlist_performance';
END
ELSE
    PRINT 'Table already exists: watchlist_performance';
GO

-- ─── breakout_entries ──────────────────────────────────────────────────────
-- One row per stock per day that triggers an active breakout signal.
-- Linked to watchlist_entries when the stock was on today's watchlist.

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[breakout_entries]')
    AND type IN (N'U')
)
BEGIN
    CREATE TABLE [dbo].[breakout_entries] (
        id                          INT IDENTITY(1,1) PRIMARY KEY,
        scan_date                   DATE NOT NULL,
        ticker                      VARCHAR(10) NOT NULL,
        company_name                VARCHAR(100) NULL,

        -- Breakout event
        breakout_price              DECIMAL(10,4) NULL,   -- price at moment of breakout detection
        pivot_price                 DECIMAL(10,4) NULL,   -- base high (the line that was broken)
        breakout_volume             BIGINT        NULL,   -- cumulative volume at detection time
        avg_volume_20d              BIGINT        NULL,
        volume_ratio                DECIMAL(5,3)  NULL,   -- breakout_volume / avg_volume_20d
        candle_close_pct            DECIMAL(5,2)  NULL,   -- % below intraday high (R25)

        -- Preceding setup metrics (from Stage 2-4)
        prior_move_pct              DECIMAL(5,2)  NULL,
        prior_move_days             INT           NULL,
        base_depth_pct              DECIMAL(5,2)  NULL,
        base_duration_days          INT           NULL,
        volume_contraction_ratio    DECIMAL(5,3)  NULL,
        adr_pct                     DECIMAL(5,2)  NULL,
        avg_daily_volume            BIGINT        NULL,
        ma10_above_ma20             BIT           NULL,
        above_50d_ma                BIT           NULL,

        -- Risk management at time of breakout
        stop_price                  DECIMAL(10,4) NULL,   -- base_low * 0.995
        atr_14                      DECIMAL(10,4) NULL,
        risk_per_share              DECIMAL(10,4) NULL,   -- breakout_price - stop_price
        suggested_rr_ratio          DECIMAL(5,2)  NULL,   -- target R/R (>= 2:1)

        -- Pattern identification
        pattern_type                VARCHAR(20)   NULL,
        pattern_grade               VARCHAR(2)    NULL,
        is_episodic_pivot           BIT           DEFAULT 0,
        catalyst_notes              NVARCHAR(500) NULL,

        -- Market conditions
        sp500_above_50d_ma          BIT           NULL,
        sp500_above_200d_ma         BIT           NULL,
        vix_level                   DECIMAL(5,2)  NULL,
        sector_trend                VARCHAR(20)   NULL,   -- 'Uptrend', 'Neutral', 'Downtrend'

        -- Qualifying reasons
        qualification_reasons       NVARCHAR(MAX) NULL,

        -- Watchlist cross-reference
        was_on_watchlist            BIT           DEFAULT 0,
        watchlist_entry_id          INT           NULL,

        created_at                  DATETIME DEFAULT GETDATE(),

        CONSTRAINT FK_breakout_entries_watchlist
            FOREIGN KEY (watchlist_entry_id) REFERENCES watchlist_entries(id)
    );

    PRINT 'Created table: breakout_entries';
END
ELSE
    PRINT 'Table already exists: breakout_entries';
GO

-- ─── breakout_performance ──────────────────────────────────────────────────
-- Tracks price and outcome after each detected breakout.

IF NOT EXISTS (
    SELECT 1 FROM sys.objects
    WHERE object_id = OBJECT_ID(N'[dbo].[breakout_performance]')
    AND type IN (N'U')
)
BEGIN
    CREATE TABLE [dbo].[breakout_performance] (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        breakout_id         INT NOT NULL,
        ticker              VARCHAR(10) NULL,
        breakout_date       DATE NULL,
        breakout_price      DECIMAL(10,4) NULL,
        stop_price          DECIMAL(10,4) NULL,

        -- Price snapshots
        price_1d            DECIMAL(10,4) NULL,
        price_3d            DECIMAL(10,4) NULL,
        price_5d            DECIMAL(10,4) NULL,
        price_10d           DECIMAL(10,4) NULL,
        price_20d           DECIMAL(10,4) NULL,
        price_60d           DECIMAL(10,4) NULL,

        -- % change from breakout price
        pct_change_1d       DECIMAL(6,2)  NULL,
        pct_change_5d       DECIMAL(6,2)  NULL,
        pct_change_10d      DECIMAL(6,2)  NULL,
        pct_change_20d      DECIMAL(6,2)  NULL,
        pct_change_60d      DECIMAL(6,2)  NULL,

        -- Trade outcome simulation
        hit_stop            BIT           NULL,    -- price touched stop_price
        hit_stop_date       DATE          NULL,
        max_r_multiple      DECIMAL(5,2)  NULL,    -- max (high - entry) / (entry - stop) achieved
        max_gain_pct        DECIMAL(6,2)  NULL,
        max_gain_date       DATE          NULL,
        was_failed_breakout BIT           NULL,    -- closed back below pivot within 3 days

        updated_at          DATETIME DEFAULT GETDATE(),

        CONSTRAINT FK_breakout_performance_entry
            FOREIGN KEY (breakout_id) REFERENCES breakout_entries(id)
    );

    PRINT 'Created table: breakout_performance';
END
ELSE
    PRINT 'Table already exists: breakout_performance';
GO

-- ─── Indexes ───────────────────────────────────────────────────────────────

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_watchlist_entries_scan_date_ticker')
    CREATE INDEX IX_watchlist_entries_scan_date_ticker
        ON watchlist_entries (scan_date, ticker);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_watchlist_entries_ticker')
    CREATE INDEX IX_watchlist_entries_ticker
        ON watchlist_entries (ticker);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_watchlist_performance_watchlist_id')
    CREATE INDEX IX_watchlist_performance_watchlist_id
        ON watchlist_performance (watchlist_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_breakout_entries_scan_date_ticker')
    CREATE INDEX IX_breakout_entries_scan_date_ticker
        ON breakout_entries (scan_date, ticker);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_breakout_entries_watchlist_id')
    CREATE INDEX IX_breakout_entries_watchlist_id
        ON breakout_entries (watchlist_entry_id);
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_breakout_performance_breakout_id')
    CREATE INDEX IX_breakout_performance_breakout_id
        ON breakout_performance (breakout_id);
GO


-- ─────────────────────────────────────────────────────────────────────────────
-- runner_entries: Stage 1+2 passes that are still in markup (no base yet)
-- ─────────────────────────────────────────────────────────────────────────────

IF NOT EXISTS (SELECT 1 FROM sys.tables WHERE name = 'runner_entries')
BEGIN
    CREATE TABLE runner_entries (
        id                  INT IDENTITY(1,1) PRIMARY KEY,
        scan_date           DATE          NOT NULL,
        ticker              VARCHAR(10)   NOT NULL,
        price_at_scan       DECIMAL(10,4),
        pct_1m              DECIMAL(6,2),
        pct_3m              DECIMAL(6,2),
        pct_6m              DECIMAL(6,2),
        pct_from_52w_high   DECIMAL(6,2),
        pct_from_20d_high   DECIMAL(6,2),
        prior_move_pct      DECIMAL(6,2),
        prior_move_days     INT,
        adr_pct             DECIMAL(5,2),
        avg_daily_volume    INT,
        created_at          DATETIME      DEFAULT GETDATE()
    );
    PRINT 'Created table: runner_entries';
END
GO

IF NOT EXISTS (SELECT 1 FROM sys.indexes WHERE name = 'IX_runner_entries_scan_date_ticker')
    CREATE UNIQUE INDEX IX_runner_entries_scan_date_ticker
        ON runner_entries (scan_date, ticker);
GO

PRINT 'Schema setup complete.';
GO
