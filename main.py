#!/usr/bin/env python3
"""
Hiroba News Smart Monitor - run.py
Usage: python run.py [--city CITY] [--lat LAT] [--lon LON] [--port PORT] [--rss URL ...]
"""

import argparse
import gzip
import json
import os
import re
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, HTTPServer

DEFAULT_RSS_FEEDS = [
    {"name": "NHK 主要",     "url": "https://www3.nhk.or.jp/rss/news/cat0.xml"},
    {"name": "BBC 日本語",   "url": "https://feeds.bbci.co.uk/japanese/rss.xml"},
    {"name": "CNN Japan",    "url": "https://feeds.cnn.co.jp/rss/cnn/cnn.rdf"},
]

DISASTER_FEEDS = [
    {"name": "気象庁 緊急情報","url": "https://www.data.jma.go.jp/developer/xml/feed/extra.xml"},
]

HENKOU_API_URL = os.environ.get("HENKOU_API_URL", "http://localhost:8000/henkou")
IMAGE_API_URL = os.environ.get("IMAGE_API_URL", "http://localhost:8000/random-image")

_cache = {}
_lock  = threading.Lock()
CACHE_TTL = 300

def cache_get(k: str):
    with _lock:
        e = _cache.get(k)
        if e and time.time() - e["ts"] < CACHE_TTL:
            return e["data"]
    return None

def cache_set(k, v):
    with _lock:
        _cache[k] = {"ts": time.time(), "data": v}

def fetch_weather(lat: int, lon: int, city: str):
    key = f"wx_{lat}_{lon}"
    if c := cache_get(key): 
        return c
    try:
        url = (f"https://api.open-meteo.com/v1/forecast"
               f"?latitude={lat}&longitude={lon}"
               f"&current=temperature_2m,apparent_temperature,weather_code,"
               f"wind_speed_10m,relative_humidity_2m,precipitation"
               f"&hourly=temperature_2m,weather_code"
               f"&daily=weather_code,temperature_2m_max,temperature_2m_min,precipitation_sum"
               f"&timezone=Asia%2FTokyo&forecast_days=7")
        with urllib.request.urlopen(url, timeout=8) as r:
            data = json.loads(r.read())

        WMO = {0:"快晴",1:"晴れ",2:"一部曇り",3:"曇り",
               45:"霧",48:"霧氷",51:"霧雨(弱)",53:"霧雨",55:"霧雨(強)",
               61:"小雨",63:"雨",65:"大雨",71:"小雪",73:"雪",75:"大雪",
               80:"にわか雨",81:"雨",82:"激しい雨",95:"雷雨",96:"雷雨+ひょう",99:"激しい雷雨"}
        ICO = {0:"☀️",1:"🌤",2:"⛅",3:"☁️",45:"🌫",48:"🌫",
               51:"🌦",53:"🌦",55:"🌧",61:"🌧",63:"🌧",65:"🌧",
               71:"🌨",73:"❄️",75:"❄️",80:"🌦",81:"🌧",82:"⛈",
               95:"⛈",96:"⛈",99:"⛈"}

        cur    = data["current"]
        code   = cur["weather_code"]
        daily  = data["daily"]
        hourly = data["hourly"]

        forecast = []
        for i in range(min(7, len(daily["time"]))):
            dc = daily["weather_code"][i]
            forecast.append({"date":daily["time"][i],"code":dc,
                              "icon":ICO.get(dc,"🌡"),"desc":WMO.get(dc,"不明"),
                              "max":round(daily["temperature_2m_max"][i],1),
                              "min":round(daily["temperature_2m_min"][i],1),
                              "precip":round(daily["precipitation_sum"][i],1)})

        hourly_data = []
        for i in range(len(hourly["time"])):
            t  = hourly["time"][i]
            h  = int(t[11:13])
            if i < 24 and h % 3 == 0:
                hc = hourly["weather_code"][i]
                hourly_data.append({"time":t[11:16],
                                    "temp":round(hourly["temperature_2m"][i],1),
                                    "icon":ICO.get(hc,"🌡")})
            if len(hourly_data) >= 8: break

        result = {"city":city,"temp":round(cur["temperature_2m"],1),
                  "feels":round(cur["apparent_temperature"],1),"code":code,
                  "icon":ICO.get(code,"🌡"),"desc":WMO.get(code,"不明"),
                  "wind":round(cur["wind_speed_10m"],1),
                  "humidity":cur["relative_humidity_2m"],
                  "precip":cur.get("precipitation",0),
                  "forecast":forecast,"hourly":hourly_data}
        cache_set(key, result)
        return result
    except Exception as e:
        return {"error":str(e),"city":city}

def fetch_henkou():
    key = "henkou_data"
    if c := cache_get(key): return c
    try:
        with urllib.request.urlopen(HENKOU_API_URL, timeout=5) as r:
            data = json.loads(r.read())
            cache_set(key, data)
            return data
    except Exception as e:
        return {"error": str(e), "items": []}

def fetch_rss(url, name, limit=20):
    key = f"rss_{url}"
    if c := cache_get(key): return c
    try:
        req = urllib.request.Request(url, headers={"User-Agent":"NewsMonitor/2.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            raw = r.read()
        root = ET.fromstring(raw)
        items = []

        for item in root.findall(".//item")[:limit]:
            title = item.findtext("title","").strip()
            link  = item.findtext("link","").strip()
            desc  = re.sub(r"<[^>]+>","",item.findtext("description",""))[:140].strip()
            pub   = item.findtext("pubDate","").strip()
            if title: items.append({"title":title,"link":link,"desc":desc,"pub":pub})

        if not items:
            ns = "http://www.w3.org/2005/Atom"
            for e in root.findall(f"{{{ns}}}entry")[:limit]:
                title = e.findtext(f"{{{ns}}}title","").strip()
                lel   = e.find(f"{{{ns}}}link")
                link  = lel.get("href","") if lel is not None else ""
                
                # Try summary first, then content
                summ = e.findtext(f"{{{ns}}}summary","")
                if not summ:
                    summ = e.findtext(f"{{{ns}}}content","")
                
                summ  = re.sub(r"<[^>]+>","", summ)[:300].strip()
                upd   = e.findtext(f"{{{ns}}}updated","")
                if title: items.append({"title":title,"link":link,"desc":summ,"pub":upd})

        res = {"name":name,"url":url,"items":items}
        cache_set(key, res)
        return res
    except Exception as e:
        return {"name":name,"url":url,"items":[],"error":str(e)}

class Handler(BaseHTTPRequestHandler):
    config = {}
    def log_message(self, *a): pass

    def _send_response(self, status, content_type, body, cache_max_age=0):
        # Apply Gzip compression if supported and beneficial
        accept_encoding = self.headers.get("Accept-Encoding", "")
        if "gzip" in accept_encoding and len(body) > 512:
            body = gzip.compress(body)
            self.send_response(status)
            self.send_header("Content-Encoding", "gzip")
        else:
            self.send_response(status)
        
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        if cache_max_age > 0:
            self.send_header("Cache-Control", f"public, max-age={cache_max_age}")
        else:
            self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        p = self.path.split("?")[0]
        if   p == "/":               self._html()
        elif p == "/api/weather":    self._json(fetch_weather(self.config["lat"],self.config["lon"],self.config["city"]))
        elif p == "/api/news":       self._json([fetch_rss(f["url"],f["name"]) for f in self.config["feeds"]])
        elif p == "/api/disaster":   self._json([fetch_rss(f["url"],f["name"],10) for f in DISASTER_FEEDS])
        elif p == "/api/henkou":     self._json(fetch_henkou())
        elif p == "/api/images":     self._json(self._imgs())
        elif p.startswith("/images/"): self._img(p)
        else: self.send_error(404)

    def _imgs(self):
        d = os.path.join(os.path.dirname(__file__),"images")
        if not os.path.isdir(d): return []
        ext = {".png",".jpg",".jpeg",".webp",".gif"}
        return ["/images/"+f for f in sorted(os.listdir(d)) if os.path.splitext(f)[1].lower() in ext]

    def _img(self, p):
        d = os.path.join(os.path.dirname(__file__),"images")
        fn = os.path.basename(p)
        fp = os.path.join(d, fn)
        if not os.path.isfile(fp): self.send_error(404); return
        mime = {".png":"image/png",".jpg":"image/jpeg",".jpeg":"image/jpeg",
                ".webp":"image/webp",".gif":"image/gif"}.get(os.path.splitext(fn)[1].lower(),"application/octet-stream")
        body = open(fp, "rb").read()
        self._send_response(200, mime, body, cache_max_age=3600)

    def _json(self, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self._send_response(200, "application/json; charset=utf-8", body)

    def _html(self):
        fp = os.path.join(os.path.dirname(__file__),"index.html")
        html = open(fp, encoding="utf-8").read()
        html = html.replace('IMAGE_API_URL = ""', f'IMAGE_API_URL = "{IMAGE_API_URL}"')
        inject = (
            f'<script>window.MONITOR_CONFIG='
            f'{{"compactClock":{str(self.config.get("compact_clock",False)).lower()},'
            f'"compactNews":{str(self.config.get("compact_news",False)).lower()},'
            f'"mouseHide":{str(self.config.get("mouse_hide",False)).lower()},'
            f'"wakeLock":{str(self.config.get("wake_lock",False)).lower()}}};</script>'
        )
        html = html.replace("</head>", inject + "</head>", 1)
        body = html.encode("utf-8")
        self._send_response(200, "text/html; charset=utf-8", body)

def main():
    ap = argparse.ArgumentParser(description="News Smart Monitor")
    ap.add_argument("--city",         default="金澤室 (高松市)", type=str)
    ap.add_argument("--lat",          default=34.3401, type=float)
    ap.add_argument("--lon",          default=134.0434, type=float)
    ap.add_argument("--port",         default=8888, type=int)
    ap.add_argument("--rss",          nargs="*")
    ap.add_argument("--no-default-rss", action="store_true")
    ap.add_argument("--compact-clock", action="store_true",
                    help="Reduce clock font size (useful on small/Linux displays)")
    ap.add_argument("--mouse-hide",    action="store_true",
                    help="Hide mouse cursor (for touch-only displays)")
    ap.add_argument("--wake-lock",     action="store_true",
                    help="Use WakeLock API to prevent screen from sleeping (Chrome/Edge/Safari)")
    args = ap.parse_args()

    feeds = [] if args.no_default_rss else list(DEFAULT_RSS_FEEDS)
    if args.rss:
        for u in args.rss:
            feeds.append({"name": urllib.parse.urlparse(u).netloc, "url": u})

    Handler.config = {"city":args.city,"lat":args.lat,"lon":args.lon,"feeds":feeds,
                      "compact_clock": args.compact_clock,
                      "mouse_hide":    args.mouse_hide,
                      "wake_lock":     args.wake_lock}

    print(f"Hiroba News Smart Monitor v1.2\nListening on all interfaces, port {args.port}")
    try:
        HTTPServer(("", args.port), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\nStopped")

if __name__ == "__main__":
    main()
