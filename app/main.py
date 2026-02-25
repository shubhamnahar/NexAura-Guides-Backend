from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import analyze, stream_ws, auth, guides # Import new routers
from . import models
from .database import engine

# Create all database tables (on startup)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- SECURITY FIX ---
# Insecure CORS configuration: allow_origins=["*"] with allow_credentials=True
# is not allowed by browsers and is a security risk.
# For browser extensions, we can use allow_origin_regex.
origins = [
    "http://localhost:3000",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_origin_regex="chrome-extension://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# -----------------------

# Include your API routers
app.include_router(analyze.router, prefix="/api/analyze", tags=["analyze"])
app.include_router(stream_ws.router, prefix="/api/ws", tags=["websocket"])
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(guides.router, prefix="/api/guides", tags=["guides"])

@app.get("/")
async def root():
    return {"message": "NexAura API is running."}