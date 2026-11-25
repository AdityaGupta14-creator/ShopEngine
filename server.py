"""FastAPI server wrapping Agent for Anticipatory Commerce demo frontend.

Provides real-time streaming endpoints for session management, word-by-word
observation, commitment detection, and session completion.
"""
import csv
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

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
            lookup[row["product_id"]] = {
                "product_id": row["product_id"],
                "title": row["title"],
                "brand": row["brand"],
                "category": row["category"],
                "colour": row["colour"],
                "size": row["size"],
                "price": int(row["price"]),
                "description": row["description"],
            }
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


class ProductInfo(BaseModel):
    product_id: str
    title: str
    brand: str
    category: str
    colour: str
    size: str
    price: int
    description: str


class ObserveResponse(BaseModel):
    filters: Dict[str, Any]
    confidence: float
    commit: Optional[str] = None
    product: Optional[ProductInfo] = None
    words_so_far: List[str]
    searches_so_far: int


class FinishRequest(BaseModel):
    session_id: str = Field(..., description="Active session ID")


class FinishResponse(BaseModel):
    final_product: Optional[ProductInfo] = None
    wasted_searches: int


class HealthResponse(BaseModel):
    status: str


# 6 Curated Example Requests (Arrays of Words)
# Covers: Plain, Correction, Late Constraint, Hindi-English, Apparel & Accessories
EXAMPLES: List[List[str]] = [
    ["I", "need", "green", "running", "shoes", "from", "Strydo", "size", "9", "under", "6000"],
    ["black", "running", "shoes,", "no", "wait,", "white,", "from", "Pacevo", "size", "10"],
    ["Can", "you", "show", "me", "a", "navy", "hoodie", "by", "Urbanyx,", "and", "make", "sure", "it", "is", "size", "S"],
    ["Bhaiya", "mujhe", "Strydo", "ke", "green", "running", "shoes", "dikhao", "8", "number", "6000", "se", "kam"],
    ["Find", "me", "a", "black", "pair", "of", "jeans", "from", "Tanaro", "waist", "32", "under", "2500"],
    ["Show", "me", "a", "blue", "wrist", "watch", "from", "Tikkra", "budget", "5k"],
]


# --- Endpoints ---


@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint."""
    return {"status": "ok"}


@app.get("/examples", response_model=List[List[str]])
def get_examples():
    """Return 6 sample shopping utterances as word arrays."""
    return EXAMPLES


@app.post("/session", response_model=SessionResponse)
def create_session():
    """Start a new agent shopping session."""
    session_id = f"session_{uuid.uuid4().hex[:12]}"
    sessions[session_id] = SessionState(session_id)
    return {"session_id": session_id}


@app.post("/observe", response_model=ObserveResponse)
def observe_word(req: ObserveRequest):
    """Feed one more word to the agent and receive current filters, commit status, product metadata, and searches."""
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
        # Keep product info available once committed
        commit_id = session.committed_product_id
        product_meta = CATALOGUE.get(commit_id)

    return {
        "filters": out.get("filters", {}),
        "confidence": out.get("confidence", 0.0),
        "commit": commit_id,
        "product": product_meta,
        "words_so_far": session.agent.words,
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
