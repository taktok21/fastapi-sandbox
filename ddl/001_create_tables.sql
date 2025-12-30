-- 物販リサーチアプリ DDL v1.0
-- MySQL 8.0

-- ============================================================
-- 1. research_job（ジョブ管理）
-- ============================================================
CREATE TABLE IF NOT EXISTS research_job (
    job_id              CHAR(36) PRIMARY KEY COMMENT 'UUID',
    status              ENUM('PENDING', 'RUNNING', 'DONE', 'FAILED') NOT NULL DEFAULT 'PENDING',

    -- ジョブ設定（計算前提の記録）
    point_rate_normal   DECIMAL(5,4) NOT NULL DEFAULT 0.01 COMMENT '通常ポイント率 (例: 0.01 = 1%)',
    point_rate_spu      DECIMAL(5,4) NOT NULL DEFAULT 0.07 COMMENT 'SPUポイント率 (例: 0.07 = 7%)',
    point_rate_total    DECIMAL(5,4) NOT NULL DEFAULT 0.08 COMMENT '合計ポイント率',

    -- 判定基準（ジョブ作成時点の設定を保存）
    threshold_profit_amount INT NOT NULL DEFAULT 1000 COMMENT '利益額閾値（円）',
    threshold_profit_rate   DECIMAL(5,4) NOT NULL DEFAULT 0.15 COMMENT '利益率閾値 (例: 0.15 = 15%)',
    threshold_rank          INT NOT NULL DEFAULT 50000 COMMENT 'ランキング閾値',
    threshold_sales_30      INT NOT NULL DEFAULT 10 COMMENT '30日販売数閾値',

    -- 集計
    total_count         INT NOT NULL DEFAULT 0 COMMENT '総件数',
    success_count       INT NOT NULL DEFAULT 0 COMMENT '成功件数',
    fail_count          INT NOT NULL DEFAULT 0 COMMENT '失敗件数',
    review_count        INT NOT NULL DEFAULT 0 COMMENT '要確認件数',
    pass_count          INT NOT NULL DEFAULT 0 COMMENT '合格件数',

    -- タイムスタンプ
    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    started_at          DATETIME NULL COMMENT '処理開始時刻',
    completed_at        DATETIME NULL COMMENT '処理完了時刻',

    INDEX idx_job_status (status),
    INDEX idx_job_created (created_at DESC)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 2. research_item（ASINの結果：一覧の主テーブル）
-- ============================================================
CREATE TABLE IF NOT EXISTS research_item (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id              CHAR(36) NOT NULL,
    asin                VARCHAR(20) NOT NULL,

    -- 処理ステータス
    process_status      ENUM('PENDING', 'PROCESSING', 'SUCCESS', 'FAILED', 'SKIPPED') NOT NULL DEFAULT 'PENDING',
    fail_reason         VARCHAR(500) NULL COMMENT '失敗理由',

    -- 商品基本情報（Keepa/SP-API）
    title               VARCHAR(500) NULL,
    jan_code            VARCHAR(20) NULL,
    model_number        VARCHAR(100) NULL COMMENT '型番',
    brand               VARCHAR(200) NULL,
    category            VARCHAR(200) NULL,

    -- Amazon価格・手数料
    amazon_price_fba_lowest     INT NULL COMMENT '最安FBA価格（円）',
    amazon_fee_referral         INT NULL COMMENT '販売手数料（円）',
    amazon_fee_fba              INT NULL COMMENT 'FBA手数料（円）',
    amazon_fee_other            INT NULL COMMENT 'その他手数料（円）',
    amazon_fee_total            INT NULL COMMENT 'Amazon手数料合計（円）',
    amazon_payout               INT NULL COMMENT '入金価格（販売価格 - 手数料）',

    -- 楽天仕入れ
    rakuten_match_type          ENUM('JAN', 'MODEL', 'NONE', 'UNKNOWN') NULL COMMENT '一致タイプ',
    rakuten_item_name           VARCHAR(500) NULL,
    rakuten_shop_name           VARCHAR(200) NULL,
    rakuten_item_url            VARCHAR(1000) NULL,
    rakuten_price               INT NULL COMMENT '楽天商品価格（円）',
    rakuten_shipping            INT NULL COMMENT '楽天送料（円）、NULLはUNKNOWN',
    rakuten_shipping_status     ENUM('FREE', 'PAID', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    rakuten_point               INT NULL COMMENT '獲得ポイント（円相当）',
    rakuten_cost_gross          INT NULL COMMENT '楽天仕入れ総額（商品+送料）',
    rakuten_cost_net            INT NULL COMMENT '楽天仕入れ実質額（総額-ポイント）',

    -- 利益計算
    profit_amount               INT NULL COMMENT '利益額（円）',
    profit_rate                 DECIMAL(5,4) NULL COMMENT '利益率',

    -- ランキング・販売数
    rank_current                INT NULL COMMENT '現在ランキング',
    rank_avg_30                 INT NULL COMMENT '30日平均ランキング',
    rank_avg_90                 INT NULL COMMENT '90日平均ランキング',
    sales_est_30                INT NULL COMMENT '30日販売数推定',
    sales_est_90                INT NULL COMMENT '90日販売数推定',
    sales_est_180               INT NULL COMMENT '180日販売数推定',

    -- セラー情報
    seller_count                INT NULL COMMENT '総セラー数',
    fba_seller_count            INT NULL COMMENT 'FBAセラー数',
    fba_lowest_seller_count     INT NULL COMMENT '最安FBAセラー数',

    -- 季節性
    seasonality_flag            TINYINT(1) NULL DEFAULT NULL COMMENT '季節性あり: 1, なし: 0, 不明: NULL',
    seasonality_score           DECIMAL(3,2) NULL COMMENT '季節性スコア (0.00-1.00)',
    seasonality_note            VARCHAR(500) NULL,

    -- リスクフラグ
    flag_hazardous              TINYINT(1) NULL DEFAULT NULL COMMENT '危険物',
    flag_hazardous_status       ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_oversized              TINYINT(1) NULL DEFAULT NULL COMMENT '大型',
    flag_oversized_status       ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_fragile                TINYINT(1) NULL DEFAULT NULL COMMENT '割れ物',
    flag_fragile_status         ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_high_return            TINYINT(1) NULL DEFAULT NULL COMMENT '返品率高い',
    flag_high_return_status     ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_maker_restriction      TINYINT(1) NULL DEFAULT NULL COMMENT 'メーカー規制',
    flag_maker_restriction_status ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_authenticity_risk      TINYINT(1) NULL DEFAULT NULL COMMENT '真贋リスク',
    flag_authenticity_risk_status ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_listing_restriction    TINYINT(1) NULL DEFAULT NULL COMMENT '出品制限',
    flag_listing_restriction_status ENUM('AUTO', 'MANUAL', 'UNKNOWN') NULL DEFAULT 'UNKNOWN',
    flag_memo                   TEXT NULL COMMENT 'リスク備考',

    -- 判定結果
    pass_status                 ENUM('PASS', 'FAIL', 'REVIEW') NULL COMMENT '合否',
    pass_fail_reasons           JSON NULL COMMENT '不合格理由リスト',

    -- 仕入れ候補フラグ（ユーザー最終判断）
    is_candidate                TINYINT(1) NOT NULL DEFAULT 0 COMMENT '仕入れ候補',
    user_memo                   TEXT NULL COMMENT 'ユーザーメモ',

    -- タイムスタンプ
    fetched_at                  DATETIME NULL COMMENT 'データ取得時刻',
    created_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at                  DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,

    -- 複合ユニーク制約
    UNIQUE KEY uk_job_asin (job_id, asin),

    INDEX idx_item_job (job_id),
    INDEX idx_item_asin (asin),
    INDEX idx_item_process_status (process_status),
    INDEX idx_item_pass_status (pass_status),
    INDEX idx_item_profit (profit_amount DESC),
    INDEX idx_item_rank (rank_current),
    INDEX idx_item_candidate (is_candidate),
    INDEX idx_item_fetched (fetched_at DESC),

    CONSTRAINT fk_item_job FOREIGN KEY (job_id) REFERENCES research_job(job_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 3. research_timeseries（推移データ：価格/ランキング/セラー）
-- ============================================================
CREATE TABLE IF NOT EXISTS research_timeseries (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id              CHAR(36) NOT NULL,
    asin                VARCHAR(20) NOT NULL,

    metric              ENUM('PRICE', 'RANK', 'SELLER_COUNT', 'FBA_SELLER_COUNT') NOT NULL,
    recorded_date       DATE NOT NULL COMMENT 'データ日付',
    value               INT NULL COMMENT '値',
    source              ENUM('KEEPA', 'SP_API', 'MANUAL') NOT NULL DEFAULT 'KEEPA',

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uk_timeseries (job_id, asin, metric, recorded_date),

    INDEX idx_ts_job_asin (job_id, asin),
    INDEX idx_ts_metric (metric),
    INDEX idx_ts_date (recorded_date),

    CONSTRAINT fk_ts_job FOREIGN KEY (job_id) REFERENCES research_job(job_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 4. rakuten_candidate（楽天候補一覧）
-- ============================================================
CREATE TABLE IF NOT EXISTS rakuten_candidate (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    job_id              CHAR(36) NOT NULL,
    asin                VARCHAR(20) NOT NULL,

    match_type          ENUM('JAN', 'MODEL', 'KEYWORD') NOT NULL COMMENT '一致タイプ',
    match_value         VARCHAR(100) NULL COMMENT '一致した値（JAN/型番）',

    -- 楽天商品情報
    rakuten_item_code   VARCHAR(100) NULL COMMENT '楽天商品コード',
    item_name           VARCHAR(500) NULL,
    item_url            VARCHAR(1000) NULL,
    shop_code           VARCHAR(100) NULL,
    shop_name           VARCHAR(200) NULL,

    -- 価格情報
    price               INT NOT NULL COMMENT '商品価格（円）',
    shipping            INT NULL COMMENT '送料（円）、NULLは不明',
    shipping_status     ENUM('FREE', 'PAID', 'UNKNOWN') NOT NULL DEFAULT 'UNKNOWN',
    total_cost          INT NULL COMMENT '合計（商品+送料）',

    -- ポイント
    point_rate          DECIMAL(5,4) NULL COMMENT 'ポイント率',
    point_rate_used     DECIMAL(5,4) NULL COMMENT '計算に使用したポイント率',
    point_amount        INT NULL COMMENT 'ポイント額（円相当）',

    -- 採用フラグ
    is_chosen           TINYINT(1) NOT NULL DEFAULT 0 COMMENT 'この候補を採用',

    created_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,

    INDEX idx_rc_job_asin (job_id, asin),
    INDEX idx_rc_match_type (match_type),
    INDEX idx_rc_chosen (is_chosen),
    INDEX idx_rc_price (price),

    CONSTRAINT fk_rc_job FOREIGN KEY (job_id) REFERENCES research_job(job_id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 5. api_cache（APIキャッシュ：コスト・レート制限対策）
-- ============================================================
CREATE TABLE IF NOT EXISTS api_cache (
    id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    cache_key           VARCHAR(255) NOT NULL COMMENT 'キャッシュキー（API種別+識別子）',
    api_type            ENUM('KEEPA', 'SP_API_FEES', 'SP_API_PRICING', 'SP_API_CATALOG', 'SP_API_RESTRICTIONS', 'RAKUTEN_PRODUCT', 'RAKUTEN_SEARCH') NOT NULL,
    request_params      JSON NULL COMMENT 'リクエストパラメータ',
    response_data       JSON NOT NULL COMMENT 'レスポンスデータ',

    fetched_at          DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at          DATETIME NOT NULL COMMENT 'キャッシュ有効期限',

    UNIQUE KEY uk_cache_key (cache_key),

    INDEX idx_cache_type (api_type),
    INDEX idx_cache_expires (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;


-- ============================================================
-- 6. VIEW: latest_research_item（ASINごとの最新結果）
-- ============================================================
CREATE OR REPLACE VIEW latest_research_item AS
SELECT ri.*
FROM research_item ri
INNER JOIN (
    SELECT asin, MAX(fetched_at) AS max_fetched
    FROM research_item
    WHERE process_status = 'SUCCESS'
    GROUP BY asin
) latest ON ri.asin = latest.asin AND ri.fetched_at = latest.max_fetched;
