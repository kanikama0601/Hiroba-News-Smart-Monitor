import re
import xml.etree.ElementTree as ElementTree
import aiohttp

from aiocache import cached
from pydantic import BaseModel, ConfigDict
from pydantic.fields import Field
from typing_extensions import ClassVar

from deps import get_settings


class ForecastItem(BaseModel):
    date: str
    code: int
    icon: str
    desc: str
    max: float
    min: float
    precip: float


class HourlyWeatherItem(BaseModel):
    time: str
    temp: float
    icon: str


class WeatherData(BaseModel):
    city: str
    temp: float
    feels: float
    code: int
    icon: str
    desc: str
    wind: float
    humidity: int
    precip: float
    forecast: list[ForecastItem]
    hourly: list[HourlyWeatherItem]


class WeatherError(BaseModel):
    error: str
    city: str


class HenkouItem(BaseModel):
    gakunen: str = Field(alias="学年")
    gakka_class: str = Field(alias="学科・クラス")
    tsukihi: str = Field(alias="月日")
    youbi: str = Field(alias="曜日")
    jigen: str = Field(alias="時限")
    henkou_naiyou: str = Field(alias="変更内容")
    kamoku_tanto: str | None = Field(None, alias="科目(担当教員)")

    model_config: ClassVar[ConfigDict] = ConfigDict(strict=True, populate_by_name=True)


class HenkouError(BaseModel):
    error: str
    items: list[HenkouItem]


class RssItem(BaseModel):
    title: str
    link: str
    desc: str
    pub: str


class RssFeed(BaseModel):
    name: str
    url: str
    items: list[RssItem]
    error: str | None = None


@cached(ttl=60 * 5, skip_cache_func=lambda res: isinstance(res, WeatherError))
async def fetch_weather(
    lat: float, lon: float, city: str
) -> WeatherData | WeatherError:
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={lat}&longitude={lon}"
            f"&current=temperature_2m,apparent_temperature,weather_code,"
            f"wind_speed_10m,relative_humidity_2m,precipitation"
            f"&hourly=temperature_2m,weather_code"
            f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
            f"&timezone=Asia%2FTokyo&forecast_days=7"
        )
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(8)) as r:
                data = await r.json()

        WMO = {
            0: "快晴",
            1: "晴れ",
            2: "一部曇り",
            3: "曇り",
            45: "霧",
            48: "霧氷",
            51: "霧雨(弱)",
            53: "霧雨",
            55: "霧雨(強)",
            61: "小雨",
            63: "雨",
            65: "大雨",
            71: "小雪",
            73: "雪",
            75: "大雪",
            80: "にわか雨",
            81: "雨",
            82: "激しい雨",
            95: "雷雨",
            96: "雷雨+ひょう",
            99: "激しい雷雨",
        }
        ICO = {
            0: "☀️",
            1: "🌤",
            2: "⛅",
            3: "☁️",
            45: "🌫",
            48: "🌫",
            51: "🌦",
            53: "🌦",
            55: "🌧",
            61: "🌧",
            63: "🌧",
            65: "🌧",
            71: "🌨",
            73: "❄️",
            75: "❄️",
            80: "🌦",
            81: "🌧",
            82: "⛈",
            95: "⛈",
            96: "⛈",
            99: "⛈",
        }

        cur = data["current"]
        code = cur["weather_code"]
        daily = data["daily"]
        hourly = data["hourly"]

        forecast: list[ForecastItem] = []
        for i in range(min(7, len(daily["time"]))):
            dc = daily["weather_code"][i]
            forecast.append(
                ForecastItem(
                    date=daily["time"][i],
                    code=dc,
                    icon=ICO.get(dc, "🌡"),
                    desc=WMO.get(dc, "不明"),
                    max=round(daily["temperature_2m_max"][i], 1),
                    min=round(daily["temperature_2m_min"][i], 1),
                    precip=round(daily["precipitation_sum"][i], 1),
                )
            )

        hourly_data: list[HourlyWeatherItem] = []
        for i in range(len(hourly["time"])):
            t = hourly["time"][i]
            h = int(t[11:13])
            if i < 24 and h % 3 == 0:
                hc = hourly["weather_code"][i]
                hourly_data.append(
                    HourlyWeatherItem(
                        time=t[11:16],
                        temp=round(hourly["temperature_2m"][i], 1),
                        icon=ICO.get(hc, "🌡"),
                    )
                )
            if len(hourly_data) >= 8:
                break

        result = WeatherData(
            city=city,
            temp=round(cur["temperature_2m"], 1),
            feels=round(cur["apparent_temperature"], 1),
            code=code,
            icon=ICO.get(code, "🌡"),
            desc=WMO.get(code, "不明"),
            wind=round(cur["wind_speed_10m"], 1),
            humidity=cur["relative_humidity_2m"],
            precip=cur.get("precipitation", 0),
            forecast=forecast,
            hourly=hourly_data,
        )
    except Exception as e:
        result = WeatherError(
            error=str(e),
            city=city,
        )

    return result


@cached(ttl=60 * 5, skip_cache_func=lambda res: isinstance(res, HenkouError))
async def fetch_henkou() -> list[HenkouItem] | HenkouError:
    try:
        url = f"{get_settings().WORKER_URL}/henkou"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(5)) as r:
                data = await r.json()
                return [HenkouItem.model_validate(item) for item in data]
    except aiohttp.ClientError as e:
        return HenkouError(
            error=f"通信エラー: {str(e)}",
            items=[],
        )
    except Exception as e:
        return HenkouError(
            error=str(e),
            items=[],
        )


@cached(
    ttl=60 * 5,
    skip_cache_func=lambda res: isinstance(res, RssFeed) and res.error is not None,
)
async def fetch_rss(url: str, name: str, limit: int = 20) -> RssFeed:
    try:
        async with aiohttp.ClientSession() as session:
            headers = {"User-Agent": "NewsMonitor/2.0"}
            async with session.get(
                url, headers=headers, timeout=aiohttp.ClientTimeout(8)
            ) as r:
                raw = await r.read()

        root = ElementTree.fromstring(raw)
        items: list[RssItem] = []

        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title", "").strip()
            link = item.findtext("link", "").strip()
            desc = re.sub(r"<[^>]+>", "", item.findtext("description", ""))[
                :140
            ].strip()
            pub = item.findtext("pubDate", "").strip()
            if title:
                items.append(RssItem(title=title, link=link, desc=desc, pub=pub))

        if not items:
            ns = "http://www.w3.org/2005/Atom"
            for e in root.findall(f"{{{ns}}}entry")[:limit]:
                title = e.findtext(f"{{{ns}}}title", "").strip()
                lel = e.find(f"{{{ns}}}link")
                link = lel.get("href", "") if lel is not None else ""

                # Try summary first, then content
                summ = e.findtext(f"{{{ns}}}summary", "")
                if not summ:
                    summ = e.findtext(f"{{{ns}}}content", "")

                summ = re.sub(r"<[^>]+>", "", summ)[:300].strip()
                upd = e.findtext(f"{{{ns}}}updated", "")
                if title:
                    items.append(RssItem(title=title, link=link, desc=summ, pub=upd))

        return RssFeed(name=name, url=url, items=items)
    except Exception as e:
        return RssFeed(name=name, url=url, items=[], error=str(e))
