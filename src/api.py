import asyncio
from fastapi import APIRouter

from deps import get_settings
from external import (
    HenkouError,
    HenkouItem,
    RssFeed,
    WeatherData,
    WeatherError,
    fetch_henkou,
    fetch_rss,
    fetch_weather,
)


router = APIRouter(prefix="/api", tags=["api"])


@router.get(
    path="/weather",
    description="現在の天気情報を取得します。",
)
async def get_weather() -> WeatherData | WeatherError:
    settings = get_settings()
    data = await fetch_weather(
        lat=settings.LATITUDE,
        lon=settings.LONGITUDE,
        city=settings.CITY_NAME,
    )
    return data


@router.get(path="/news", description="ニュースのRSSフィードを取得します。")
async def get_news() -> list[RssFeed]:
    news = [fetch_rss(f["url"], f["name"]) for f in get_settings().get_feeds]
    return await asyncio.gather(*news)  # pyright: ignore[reportUnknownArgumentType]


@router.get(path="/disaster", description="災害情報のRSSフィードを取得します。")
async def get_disaster() -> list[RssFeed]:
    disaster = [
        fetch_rss(f["url"], f["name"], 10) for f in get_settings().DISASTER_FEEDS
    ]
    return await asyncio.gather(*disaster)  # pyright: ignore[reportUnknownArgumentType]


@router.get(path="/henkou", description="時間割変更情報を取得します。")
async def get_henkou() -> list[HenkouItem] | HenkouError:
    data = await fetch_henkou()
    return data
