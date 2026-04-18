from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape

import api
from deps import get_settings

app = FastAPI()
app.mount("/styles", StaticFiles(directory="styles"), name="styles")
app.include_router(api.router)

templates = Environment(
    loader=FileSystemLoader("templates"),
    autoescape=select_autoescape(("html", "xml")),
)


@app.get("/")
async def get_index() -> HTMLResponse:
    settings = get_settings()
    backend_url = settings.BACKEND_URL.rstrip("/")
    template = templates.get_template("index.html")
    html = template.render(
        BACKEND_URL=backend_url,
        MONITOR_CONFIG={
            "compactClock": settings.COMPACT_CLOCK,
            "compactNews": False,
            "mouseHide": settings.MOUSE_HIDE,
            "wakeLock": settings.WAKE_LOCK,
        },
    )
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=get_settings().PORT)
