"""FastAPI server wrapping Agent for Anticipatory Commerce demo frontend.

Provides real-time streaming endpoints for session management, word-by-word
observation, commitment detection, and session completion.
"""
import csv
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent import Agent
from search import search

CATALOGUE_PATH = Path(__file__).resolve().parent / "catalogue.csv"


def load_catalogue_lookup() -> Dict[str, Dict[str, Any]]:
    """Load catalogue products into memory for quick O(1) metadata lookups."""
    lookup = {}
    with open(CATALOGUE_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            row["price"] = int(row["price"])
            lookup[row["product_id"]] = row
    return lookup


CATALOGUE = load_catalogue_lookup()


class Tools:
    """Search tools wrapper preserving the search counter."""

    def __init__(self):
        self.searches = 0

    def search(self, query="", filters=None, k=10):
        self.searches += 1
        return search(query, filters, k)

    def record_search(self, n=1):
        self.searches += n


class SessionState:
    """Encapsulates in-memory session state for an active agent interaction."""

    def __init__(self, session_id: str):
        self.session_id = session_id
        self.tools = Tools()
        self.agent = Agent(self.tools)
        self.agent.start(session_id)
        self.committed_product_id: Optional[str] = None


# In-memory storage of active sessions
sessions: Dict[str, SessionState] = {}

app = FastAPI(
    title="Anticipatory Commerce Agent API",
    description="FastAPI service for real-time word-by-word anticipatory shopping agent demo.",
    version="1.0.0",
)

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- Request and Response Models ---


class SessionResponse(BaseModel):
    session_id: str


class ObserveRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID")
    word: str = Field(..., description="Word streamed to the agent")


class ObserveResponse(BaseModel):
    filters: Dict[str, Any]
    confidence: float
    commit: Optional[str] = None
    product: Optional[Dict[str, Any]] = None
    searches_so_far: int


class FinishRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID")


class FinishResponse(BaseModel):
    final_product: Optional[Dict[str, Any]] = None
    wasted_searches: int


class HealthResponse(BaseModel):
    status: str


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.post("/session", response_model=SessionResponse)
def create_session():
    """Start a new agent shopping session."""
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    sessions[session_id] = SessionState(session_id)
    return {"session_id": session_id}


@app.post("/observe", response_model=ObserveResponse)
def observe_word(req: ObserveRequest):
    """Feed one more word to the agent and receive current filters, commit status, and searches."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    out = session.agent.observe(req.word) or {}

    commit_id = out.get("commit")
    product_meta = None

    if commit_id:
        session.committed_product_id = commit_id
        product_meta = CATALOGUE.get(commit_id)
    elif session.committed_product_id:
        # Keep product info available if already committed
        commit_id = session.committed_product_id
        product_meta = CATALOGUE.get(commit_id)

    return {
        "filters": out.get("filters", {}),
        "confidence": out.get("confidence", 0.0),
        "commit": commit_id,
        "product": product_meta,
        "searches_so_far": session.tools.searches,
    }


@app.post("/finish", response_model=FinishResponse)
def finish_session(req: FinishRequest):
    """Complete the request, return final product and wasted searches count."""
    session = sessions.get(req.session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    final_product_id = session.agent.finish() or session.committed_product_id
    final_product = CATALOGUE.get(final_product_id) if final_product_id else None
    wasted_searches = max(0, session.tools.searches - 1)

    return {
        "final_product": final_product,
        "wasted_searches": wasted_searches,
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("server:app", host="0.0.0.0", port=8000, reload=True)
