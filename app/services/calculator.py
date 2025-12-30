"""
利益計算ロジック

計算式:
- 入金価格 = 販売価格（最安FBA） - Amazon手数料
- 仕入れ価格 = 楽天価格 + 送料 - ポイント
- 利益額 = 入金価格 - 仕入れ価格
- 利益率 = 利益額 / 入金価格

判定基準（デフォルト）:
- 利益額 >= 1,000円
- 利益率 >= 15%
- ランキング <= 50,000位
- 30日販売数 >= 10個
"""
import logging
from typing import Optional, List
from decimal import Decimal, ROUND_HALF_UP

from app.models.item import ResearchItem
from app.models.job import ResearchJob

logger = logging.getLogger(__name__)


class ProfitCalculator:
    """利益計算クラス"""

    def __init__(self, job: ResearchJob):
        self.job = job
        self.threshold_profit_amount = job.threshold_profit_amount
        self.threshold_profit_rate = Decimal(str(job.threshold_profit_rate))
        self.threshold_rank = job.threshold_rank
        self.threshold_sales_30 = job.threshold_sales_30

    def calculate(self, item: ResearchItem) -> dict:
        """
        利益を計算

        Args:
            item: ResearchItem（Amazon/楽天データ設定済み）

        Returns:
            {
                'amazon_payout': int,      # 入金価格
                'profit_amount': int,      # 利益額
                'profit_rate': Decimal,    # 利益率
            }
        """
        result = {
            'amazon_payout': None,
            'profit_amount': None,
            'profit_rate': None,
        }

        # Amazon入金価格
        if item.amazon_price_fba_lowest and item.amazon_fee_total is not None:
            result['amazon_payout'] = item.amazon_price_fba_lowest - item.amazon_fee_total
        elif item.amazon_payout:
            result['amazon_payout'] = item.amazon_payout

        # 楽天仕入れ価格
        rakuten_cost = item.rakuten_cost_net
        if rakuten_cost is None and item.rakuten_price:
            # rakuten_cost_netが未計算の場合
            shipping = item.rakuten_shipping or 0
            point = item.rakuten_point or 0
            rakuten_cost = item.rakuten_price + shipping - point

        # 利益計算
        if result['amazon_payout'] and rakuten_cost:
            result['profit_amount'] = result['amazon_payout'] - rakuten_cost

            # 利益率（入金価格ベース）
            if result['amazon_payout'] > 0:
                rate = Decimal(result['profit_amount']) / Decimal(result['amazon_payout'])
                result['profit_rate'] = rate.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)

        return result

    def evaluate(self, item: ResearchItem) -> dict:
        """
        合否判定

        Args:
            item: ResearchItem（利益計算済み）

        Returns:
            {
                'pass_status': 'PASS' | 'FAIL' | 'REVIEW',
                'reasons': List[str],
            }
        """
        reasons = []
        review_reasons = []

        # 利益額チェック
        if item.profit_amount is not None:
            if item.profit_amount < self.threshold_profit_amount:
                reasons.append(f"利益額{item.profit_amount:,}円 < {self.threshold_profit_amount:,}円")
        else:
            review_reasons.append("利益額が計算できません")

        # 利益率チェック
        if item.profit_rate is not None:
            rate = Decimal(str(item.profit_rate))
            if rate < self.threshold_profit_rate:
                pct = float(rate * 100)
                threshold_pct = float(self.threshold_profit_rate * 100)
                reasons.append(f"利益率{pct:.1f}% < {threshold_pct:.1f}%")
        else:
            review_reasons.append("利益率が計算できません")

        # ランキングチェック
        if item.rank_current is not None:
            if item.rank_current > self.threshold_rank:
                reasons.append(f"ランキング{item.rank_current:,}位 > {self.threshold_rank:,}位")
        else:
            review_reasons.append("ランキングが不明")

        # 30日販売数チェック
        if item.sales_est_30 is not None:
            if item.sales_est_30 < self.threshold_sales_30:
                reasons.append(f"30日販売数{item.sales_est_30}個 < {self.threshold_sales_30}個")
        else:
            review_reasons.append("30日販売数が不明")

        # 楽天マッチング
        if item.rakuten_match_type == 'NONE':
            reasons.append("楽天で同一商品が見つかりません")
        elif item.rakuten_match_type == 'UNKNOWN':
            review_reasons.append("楽天マッチング未実行")

        # 送料不明
        if item.rakuten_shipping_status == 'UNKNOWN':
            review_reasons.append("楽天送料が不明")

        # 判定
        if reasons:
            return {
                'pass_status': 'FAIL',
                'reasons': reasons,
            }
        elif review_reasons:
            return {
                'pass_status': 'REVIEW',
                'reasons': review_reasons,
            }
        else:
            return {
                'pass_status': 'PASS',
                'reasons': [],
            }

    def calculate_and_evaluate(self, item: ResearchItem) -> dict:
        """
        計算と判定を一括実行してitemを更新

        Returns:
            {
                'pass_status': str,
                'reasons': List[str],
            }
        """
        # 計算
        calc_result = self.calculate(item)
        item.amazon_payout = calc_result['amazon_payout']
        item.profit_amount = calc_result['profit_amount']
        if calc_result['profit_rate'] is not None:
            item.profit_rate = float(calc_result['profit_rate'])

        # 判定
        eval_result = self.evaluate(item)
        item.pass_status = eval_result['pass_status']
        item.pass_fail_reasons = eval_result['reasons'] if eval_result['reasons'] else None

        return eval_result


def calculate_rakuten_cost(
    price: int,
    shipping: Optional[int],
    point_rate: float,
) -> dict:
    """
    楽天仕入れコストを計算

    Args:
        price: 商品価格
        shipping: 送料（Noneは不明）
        point_rate: ポイント率（合計）

    Returns:
        {
            'gross_cost': int,  # 総額（価格+送料）
            'point': int,       # ポイント額
            'net_cost': int,    # 実質額（総額-ポイント）
        }
    """
    shipping_val = shipping if shipping is not None else 0
    gross_cost = price + shipping_val
    point = int(gross_cost * point_rate)
    net_cost = gross_cost - point

    return {
        'gross_cost': gross_cost,
        'point': point,
        'net_cost': net_cost,
    }
