"""
RQタスク定義
1次スクリーニング: Keepa
2次確定: SP-API + 楽天
"""
import logging
from datetime import datetime, date
from typing import Optional

from redis import Redis
from rq import Queue

from app.config import get_settings
from app.database import SessionLocal
from app.models.job import ResearchJob
from app.models.item import ResearchItem
from app.models.timeseries import ResearchTimeseries
from app.services.job_service import JobService
from app.services.keepa import KeepaService
from app.services.sp_api import SpApiService
from app.services.rakuten import RakutenService
from app.services.calculator import ProfitCalculator, calculate_rakuten_cost

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis接続
redis_conn = Redis.from_url(settings.redis_url)
research_queue = Queue("research", connection=redis_conn)


def enqueue_research_job(job_id: str) -> str:
    """リサーチジョブをキューに追加"""
    job = research_queue.enqueue(
        process_research_job,
        job_id,
        job_timeout="1h",
        result_ttl=86400,
    )
    return job.id


def process_research_job(job_id: str) -> dict:
    """
    リサーチジョブを処理
    1次スクリーニング: Keepa取得
    2次確定: SP-API + 楽天
    """
    db = SessionLocal()
    try:
        # ジョブステータス更新
        job = JobService.update_job_status(db, job_id, "RUNNING")
        if not job:
            return {"error": f"Job {job_id} not found"}

        logger.info(f"Starting research job: {job_id}")

        # 処理待ちアイテムを取得
        pending_items = JobService.get_pending_items(db, job_id, limit=1000)

        processed = 0
        for item in pending_items:
            try:
                process_single_item(db, item, job)
                processed += 1
            except Exception as e:
                logger.error(f"Error processing ASIN {item.asin}: {e}")
                item.process_status = "FAILED"
                item.fail_reason = str(e)[:500]
                db.commit()

        # 集計更新
        JobService.update_job_counts(db, job_id)

        # ジョブ完了
        JobService.update_job_status(db, job_id, "DONE")

        logger.info(f"Completed research job: {job_id}, processed: {processed}")
        return {"job_id": job_id, "processed": processed}

    except Exception as e:
        logger.error(f"Job {job_id} failed: {e}")
        JobService.update_job_status(db, job_id, "FAILED")
        raise
    finally:
        db.close()


def process_single_item(db: SessionLocal, item: ResearchItem, job: ResearchJob) -> None:
    """
    単一ASINの処理
    1次: Keepaでランキング/販売数を取得（スクリーニング）
    2次: SP-API + 楽天 + 利益計算
    """
    item.process_status = "PROCESSING"
    db.commit()

    try:
        # ========== 1次スクリーニング: Keepa ==========
        keepa_service = KeepaService(db)
        try:
            keepa_data = fetch_keepa_data(keepa_service, item, job)
        finally:
            keepa_service.close()

        # Keepaデータがない場合はスキップ
        if not keepa_data:
            item.process_status = "FAILED"
            item.fail_reason = "Keepa data not available"
            db.commit()
            return

        # 1次スクリーニング: ランキング・販売数チェック
        if not pass_first_screening(item, job):
            item.process_status = "SUCCESS"
            item.pass_status = "FAIL"
            item.pass_fail_reasons = ["1次スクリーニング不合格（ランキング/販売数）"]
            item.fetched_at = datetime.utcnow()
            db.commit()
            return

        # ========== 2次確定: SP-API ==========
        fetch_sp_api_data(db, item, job)

        # ========== 楽天検索 ==========
        fetch_rakuten_data(db, item, job)

        # ========== 利益計算・判定 ==========
        calculator = ProfitCalculator(job)
        calculator.calculate_and_evaluate(item)

        # 完了
        item.process_status = "SUCCESS"
        item.fetched_at = datetime.utcnow()
        db.commit()

    except Exception as e:
        logger.error(f"Error processing {item.asin}: {e}")
        item.process_status = "FAILED"
        item.fail_reason = str(e)[:500]
        db.commit()
        raise


def fetch_sp_api_data(db: SessionLocal, item: ResearchItem, job: ResearchJob) -> None:
    """
    SP-APIからデータを取得してitemに反映
    - 最安FBA価格
    - 手数料見積もり
    - 出品制限
    """
    sp_api = SpApiService(db)

    try:
        # 1. オファー情報（最安FBA価格）
        offers = sp_api.get_item_offers(item.asin)
        if offers:
            item.amazon_price_fba_lowest = offers.get('fba_lowest_price')
            if offers.get('fba_seller_count'):
                item.fba_seller_count = offers.get('fba_seller_count')
            if offers.get('seller_count'):
                item.seller_count = offers.get('seller_count')

        # 2. 手数料見積もり（価格がある場合のみ）
        if item.amazon_price_fba_lowest:
            fees = sp_api.get_fees_estimate(item.asin, item.amazon_price_fba_lowest)
            if fees:
                item.amazon_fee_referral = fees.get('referral_fee')
                item.amazon_fee_fba = fees.get('fba_fee')
                item.amazon_fee_other = fees.get('other_fee')
                item.amazon_fee_total = fees.get('total_fee')
                # 入金価格計算
                item.amazon_payout = item.amazon_price_fba_lowest - (item.amazon_fee_total or 0)

        # 3. カタログ情報（JAN/型番補完）
        if not item.jan_code or not item.model_number:
            catalog = sp_api.get_catalog_item(item.asin)
            if catalog:
                if not item.jan_code:
                    item.jan_code = catalog.get('ean')
                if not item.model_number:
                    item.model_number = catalog.get('model_number') or catalog.get('part_number')
                if not item.title:
                    item.title = catalog.get('title')
                if not item.brand:
                    item.brand = catalog.get('brand')

        # 4. 出品制限
        restrictions = sp_api.get_listing_restrictions(item.asin)
        if restrictions:
            if restrictions.get('has_restriction') is True:
                item.flag_listing_restriction = True
                item.flag_listing_restriction_status = 'AUTO'
            elif restrictions.get('has_restriction') is False:
                item.flag_listing_restriction = False
                item.flag_listing_restriction_status = 'AUTO'
            else:
                item.flag_listing_restriction_status = 'UNKNOWN'

        db.commit()

    except Exception as e:
        logger.warning(f"SP-API error for {item.asin}: {e}")
        # SP-APIエラーは致命的ではない（続行）


def fetch_rakuten_data(db: SessionLocal, item: ResearchItem, job: ResearchJob) -> None:
    """
    楽天からデータを取得してitemに反映
    """
    rakuten = RakutenService(db)

    try:
        point_rate = float(job.point_rate_total)

        result = rakuten.find_matching_items(
            jan_code=item.jan_code,
            model_number=item.model_number,
            job_id=job.job_id,
            asin=item.asin,
            point_rate=point_rate,
        )

        # マッチタイプ
        item.rakuten_match_type = result.get('match_type', 'NONE')

        # 最安候補
        chosen = result.get('chosen_item')
        if chosen:
            item.rakuten_item_name = chosen.get('item_name')
            item.rakuten_shop_name = chosen.get('shop_name')
            item.rakuten_item_url = chosen.get('item_url')
            item.rakuten_price = chosen.get('price')
            item.rakuten_shipping = chosen.get('shipping')
            item.rakuten_shipping_status = chosen.get('shipping_status', 'UNKNOWN')
            item.rakuten_point = chosen.get('point_amount')
            item.rakuten_cost_gross = chosen.get('gross_cost')
            item.rakuten_cost_net = chosen.get('net_cost')

        db.commit()

    except Exception as e:
        logger.warning(f"Rakuten error for {item.asin}: {e}")
        item.rakuten_match_type = 'UNKNOWN'
        db.commit()
    finally:
        rakuten.close()


def fetch_keepa_data(keepa_service: KeepaService, item: ResearchItem, job: ResearchJob) -> Optional[dict]:
    """
    Keepaからデータを取得してitemに反映
    """
    product = keepa_service.fetch_product(item.asin)
    if not product:
        return None

    # データを解析
    parsed = keepa_service.parse_product(product)

    # itemに反映
    item.title = parsed.get('title')
    item.brand = parsed.get('brand')
    item.category = parsed.get('category')
    item.jan_code = parsed.get('jan_code')
    item.model_number = parsed.get('model_number')
    item.rank_current = parsed.get('rank_current')
    item.rank_avg_30 = parsed.get('rank_avg_30')
    item.rank_avg_90 = parsed.get('rank_avg_90')
    item.sales_est_30 = parsed.get('sales_est_30')
    item.sales_est_90 = parsed.get('sales_est_90')
    item.sales_est_180 = parsed.get('sales_est_180')
    item.seller_count = parsed.get('seller_count')
    item.fba_seller_count = parsed.get('fba_seller_count')

    # 時系列データを保存
    save_timeseries(keepa_service.db, job.job_id, item.asin, parsed)

    return parsed


def save_timeseries(db: SessionLocal, job_id: str, asin: str, parsed: dict):
    """時系列データをDBに保存"""
    # 価格推移
    for entry in parsed.get('price_history', [])[-90:]:  # 直近90件
        ts = ResearchTimeseries(
            job_id=job_id,
            asin=asin,
            metric="PRICE",
            recorded_date=date.fromisoformat(entry['date']),
            value=entry['value'],
            source="KEEPA",
        )
        db.merge(ts)

    # ランキング推移
    for entry in parsed.get('rank_history', [])[-90:]:
        ts = ResearchTimeseries(
            job_id=job_id,
            asin=asin,
            metric="RANK",
            recorded_date=date.fromisoformat(entry['date']),
            value=entry['value'],
            source="KEEPA",
        )
        db.merge(ts)

    db.commit()


def pass_first_screening(item: ResearchItem, job: ResearchJob) -> bool:
    """
    1次スクリーニング: ランキング・販売数でフィルタ

    Returns:
        True: 2次確定に進む
        False: 不合格
    """
    reasons = []

    # ランキングチェック
    if item.rank_current:
        if item.rank_current > job.threshold_rank:
            reasons.append(f"ランキング{item.rank_current:,}位 > {job.threshold_rank:,}位")
    else:
        # ランキング不明は通過（2次で確認）
        pass

    # 30日販売数チェック
    if item.sales_est_30 is not None:
        if item.sales_est_30 < job.threshold_sales_30:
            reasons.append(f"30日販売数{item.sales_est_30}個 < {job.threshold_sales_30}個")
    else:
        # 販売数不明は通過（2次で確認）
        pass

    if reasons:
        item.pass_fail_reasons = reasons
        return False

    return True
