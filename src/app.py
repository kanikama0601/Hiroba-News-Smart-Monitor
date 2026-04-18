from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import api
from deps import get_settings

app = FastAPI()
app.mount("/styles", StaticFiles(directory="styles"), name="styles")
app.include_router(api.router)

templates = Jinja2Templates(directory="templates")


@app.get("/")
async def get_index(req: Request) -> HTMLResponse:
    settings = get_settings()
    backend_url = settings.BACKEND_URL.rstrip("/")
    return templates.TemplateResponse(
        request=req,
        name="index.html",
        context={
            "BACKEND_URL": backend_url,
            "MONITOR_CONFIG": {
                "compactClock": settings.COMPACT_CLOCK,
                "compactNews": False,
                "mouseHide": settings.MOUSE_HIDE,
                "wakeLock": settings.WAKE_LOCK,
            },
        },
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=get_settings().PORT)
