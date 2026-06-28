from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.database import create_db_and_tables
from app.api.webhooks.vapi_webhook import router as vapi_router
from app.api.webhooks.twilio_webhook import router as twilio_router
from app.api.routers.leads import router as leads_router
from app.api.routers.documents import router as documents_router
from app.api.routers.lors import router as lors_router
from app.api.routers.calls import router as calls_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Wayco PI Intake API",
    description="AI-powered personal injury intake, lead scoring, and retainer closing",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vapi_router)
app.include_router(twilio_router)
app.include_router(leads_router)
app.include_router(documents_router)
app.include_router(lors_router)
app.include_router(calls_router)


@app.get("/")
def health():
    return {"status": "ok", "service": "Wayco PI Intake"}


@app.get("/health")
def health_check():
    return {"status": "healthy"}
