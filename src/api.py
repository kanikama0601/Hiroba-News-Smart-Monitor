import asyncio
import aiohttp
from fastapi import APIRouter
from fastapi.responses import StreamingResponse

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


@router.get(path="/random-image", description="ランダムな画像URLを取得します。")
async def get_random_image():
    url = f"{get_settings().WORKER_URL}/random-image"

    async def stream():
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                async for chunk in resp.content.iter_chunked(1024):
                    yield chunk


    return StreamingResponse(stream())

