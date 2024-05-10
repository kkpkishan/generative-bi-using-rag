from fastapi import FastAPI, status
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from api.exception_handler import biz_exception
from api.main import router
from fastapi.middleware.cors import CORSMiddleware
from api import service
from api.schemas import Option

app = FastAPI(title='GenBI')

# Configure CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],  # Allow access from all sources and can be modified according to needs
    allow_credentials=True,  # Allow sending credentials (such as cookies)
    allow_methods=['*'],  # Allow all HTTP methods
    allow_headers=['*'],  # Allow all request headers
)

# Global exception capture
biz_exception(app)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(router)

@app.get("/", status_code=status.HTTP_302_FOUND)
def index():
    return RedirectResponse("static/WebSocket.html")

@app.get("/option", response_model=Option)
def option():
    return service.get_option()