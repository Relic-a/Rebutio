from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from workbench.modules.coach_mode import CoachModeEngine
from workbench.modules.debate_mode import DebateModeEngine
from workbench.modules.reviewer_mode import ReviewerEngine
from workbench.modules.topic_generator import TopicGeneratorEngine
from workbench.runner import WorkbenchRunner
from workbench.state.models import (
    CoachState,
    DebateState,
    ReviewState,
    TopicGeneratorInput,
    TopicGeneratorState,
)
from workbench.state.store import StateStore

app = FastAPI(title="Rebutio Workbench API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

WEB_DIR = Path(__file__).resolve().parent / "web"


# ---------------------------------------------------------------------------
# Request Payloads
# ---------------------------------------------------------------------------

class TopicGenerateRequest(BaseModel):
    input: TopicGeneratorInput
    live: bool = False


class DebateStepRequest(BaseModel):
    debate_state: DebateState
    user_text: str
    live: bool = False


class ReviewRunRequest(BaseModel):
    debate_state: DebateState
    live: bool = False


class CoachOpeningRequest(BaseModel):
    coach_state: CoachState
    live: bool = False


class CoachChatRequest(BaseModel):
    coach_state: CoachState
    message: str
    live: bool = False


class CoachMemoryRequest(BaseModel):
    coach_state: CoachState
    live: bool = False


class SaveStateRequest(BaseModel):
    category: str
    name: str
    state_data: Dict[str, Any]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_path = WEB_DIR / "index.html"
    if not index_path.exists():
        return "<h1>Rebutio Workbench</h1><p>Web dashboard not found.</p>"
    return index_path.read_text(encoding="utf-8")


@app.get("/api/presets")
async def list_presets():
    return StateStore.list_presets()


@app.get("/api/presets/{category}/{name}")
async def get_preset(category: str, name: str):
    try:
        p_name = f"{category}/{name}"
        if category == "topics":
            return StateStore.load_state(TopicGeneratorState, p_name)
        elif category == "debates":
            return StateStore.load_state(DebateState, p_name)
        elif category == "reviews":
            return StateStore.load_state(ReviewState, p_name)
        elif category == "coach":
            return StateStore.load_state(CoachState, p_name)
        else:
            raise HTTPException(status_code=404, detail="Invalid category")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@app.post("/api/topics/generate")
async def generate_topics(req: TopicGenerateRequest):
    return await WorkbenchRunner.run_topic_generation(req.input, live=req.live)


@app.post("/api/debate/new")
async def new_debate(topic: str, user_side: str = "agree", difficulty: str = "steady", skill_id: str = "direct_refutation"):
    return StateStore.create_debate_from_topic(
        topic=topic,
        user_side=user_side,
        difficulty=difficulty,
        skill_id=skill_id,
    )


@app.post("/api/debate/step")
async def step_debate(req: DebateStepRequest):
    updated_state, opp_turn = await WorkbenchRunner.run_debate_step(
        debate_or_path=req.debate_state,
        user_text=req.user_text,
        auto_opponent=True,
        live=req.live,
    )
    return {"debate_state": updated_state, "opponent_turn": opp_turn}


@app.post("/api/review/run")
async def run_review(req: ReviewRunRequest):
    return await WorkbenchRunner.run_review(debate_or_path=req.debate_state, live=req.live)


@app.post("/api/coach/opening")
async def coach_opening(req: CoachOpeningRequest):
    coach_state, opening = await WorkbenchRunner.run_coach_opening(coach_or_path=req.coach_state, live=req.live)
    return {"coach_state": coach_state, "opening_analysis": opening}


@app.post("/api/coach/chat")
async def coach_chat(req: CoachChatRequest):
    coach_state, msg = await WorkbenchRunner.run_coach_chat(
        coach_or_path=req.coach_state,
        user_message=req.message,
        live=req.live,
    )
    return {"coach_state": coach_state, "message": msg}


@app.post("/api/coach/memory")
async def coach_memory(req: CoachMemoryRequest):
    coach_state, md, diff = await WorkbenchRunner.run_coach_memory_update(coach_or_path=req.coach_state, live=req.live)
    return {"coach_state": coach_state, "updated_markdown": md, "diff": diff}


@app.post("/api/states/save")
async def save_state_endpoint(req: SaveStateRequest):
    try:
        if req.category == "topics":
            model = TopicGeneratorState.model_validate(req.state_data)
        elif req.category == "debates":
            model = DebateState.model_validate(req.state_data)
        elif req.category == "reviews":
            model = ReviewState.model_validate(req.state_data)
        elif req.category == "coach":
            model = CoachState.model_validate(req.state_data)
        else:
            raise ValueError(f"Unknown category {req.category}")

        p = StateStore.save_state(model, filename=req.name, category=req.category)
        return {"saved_path": str(p), "name": p.name}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
