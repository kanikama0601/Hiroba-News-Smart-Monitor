from functools import cached_property
from typing import ClassVar, TypedDict
import urllib.parse

from pydantic_settings import BaseSettings, SettingsConfigDict

FeedSettingItem = TypedDict("FeedSettingItem", {"name": str, "url": str})


class Settings(BaseSettings):
    WORKER_URL: str = "http://localhost:8000"
    BACKEND_URL: str = "http://localhost:8888"
    LATITUDE: float = 34.3401
    LONGITUDE: float = 134.0434
    CITY_NAME: str = "高松"
    PORT: int = 8888
    NO_DEFAULT_FEEDS: bool = False
    RSS_FEEDS: list[str] = []
    COMPACT_CLOCK: bool = False
    MOUSE_HIDE: bool = False
    WAKE_LOCK: bool = False

    DEFAULT_RSS_FEEDS: ClassVar[list[FeedSettingItem]] = [
        {"name": "NHK 主要", "url": "https://www3.nhk.or.jp/rss/news/cat0.xml"},
        {"name": "BBC 日本語", "url": "https://feeds.bbci.co.uk/japanese/rss.xml"},
        {"name": "CNN Japan", "url": "https://feeds.cnn.co.jp/rss/cnn/cnn.rdf"},
    ]

    DISASTER_FEEDS: ClassVar[list[FeedSettingItem]] = [
        {
            "name": "気象庁 緊急情報",
            "url": "https://www.data.jma.go.jp/developer/xml/feed/extra.xml",
        },
    ]

    @cached_property
    def get_feeds(self) -> list[FeedSettingItem]:
        feeds = [] if self.NO_DEFAULT_FEEDS else self.DEFAULT_RSS_FEEDS
        for feed_url in self.RSS_FEEDS:
            feeds.append(
                {"name": urllib.parse.urlparse(feed_url).netloc, "url": feed_url}
            )
        return feeds

    model_config: ClassVar[SettingsConfigDict] = SettingsConfigDict(
        env_file=".env",
    )
