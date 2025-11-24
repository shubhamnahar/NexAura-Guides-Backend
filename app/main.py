from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routes import analyze, stream_ws, auth, guides # Import new routers
from . import models
from .database import engine

# Create all database tables (on startup)
models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# --- THIS IS THE FIX ---
# Change the origins list to ["*"] to allow
# your extension to work on any website.
origins = [
    "http://localhost:3000", # Good for development
    "*"                      # Allow all origins (for your extension)
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,  # Use the updated list
    allow_credentials=True,
    allow_methods=["*"],  # Allow all methods (GET, POST, etc.)
    allow_headers=["*"],  # Allow all headers (like Authorization)
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