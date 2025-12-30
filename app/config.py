import os
from functools import lru_cache

from dotenv import load_dotenv
from pydantic_settings import BaseSettings

load_dotenv()


class Settings(BaseSettings):
    # Database
    database_url: str = os.getenv("DATABASE_URL", "")

    # Redis
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # API Keys (環境変数から取得)
    keepa_api_key: str = os.getenv("KEEPA_API_KEY", "")
    sp_api_refresh_token: str = os.getenv("SP_API_REFRESH_TOKEN", "")
    sp_api_client_id: str = os.getenv("SP_API_CLIENT_ID", "")
    sp_api_client_secret: str = os.getenv("SP_API_CLIENT_SECRET", "")
    sp_api_marketplace_id: str = os.getenv("SP_API_MARKETPLACE_ID", "A1VC38T7YXB528")  # Japan
    sp_api_seller_id: str = os.getenv("SP_API_SELLER_ID", "")
    rakuten_app_id: str = os.getenv("RAKUTEN_APP_ID", "")

    # Cache TTL (seconds)
    cache_ttl_seconds: int = int(os.getenv("CACHE_TTL_SECONDS", "86400"))  # 24時間

    # Rate Limits (requests per second)
    rate_limit_keepa: float = float(os.getenv("RATE_LIMIT_KEEPA", "0.5"))  # 2秒に1回
    rate_limit_sp_api: float = float(os.getenv("RATE_LIMIT_SP_API", "1.0"))  # 1秒に1回
    rate_limit_rakuten: float = float(os.getenv("RATE_LIMIT_RAKUTEN", "1.0"))  # 1秒に1回

    # Default thresholds
    default_profit_amount: int = 1000
    default_profit_rate: float = 0.15
    default_rank_threshold: int = 50000
    default_sales_30_threshold: int = 10

    # Default point rates
    default_point_rate_normal: float = 0.01
    default_point_rate_spu: float = 0.07

    class Config:
        env_file = ".env"


@lru_cache
def get_settings() -> Settings:
    return Settings()
