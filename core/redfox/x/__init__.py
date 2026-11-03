"""X (Twitter) Redfox 接口与同步入口。"""
from .client import XClient, PAGE_SIZE, SEARCH_TWEETS_PATH, RedfoxError, iter_search_tweets, parse_publish_time, search_tweets
from .sync import AUTO_DISABLE_ERROR_THRESHOLD, X_KW_PREFIX, build_feed_id, do_job_x

__all__ = [
    "XClient", "RedfoxError", "PAGE_SIZE", "SEARCH_TWEETS_PATH",
    "search_tweets", "iter_search_tweets", "parse_publish_time",
    "X_KW_PREFIX", "AUTO_DISABLE_ERROR_THRESHOLD", "build_feed_id", "do_job_x",
]
