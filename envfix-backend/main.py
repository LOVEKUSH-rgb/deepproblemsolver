import uuid
from typing import List
from fastapi import FastAPI, Depends, HTTPException, Security
from fastapi.security import APIKeyHeader
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from sqlalchemy import func, desc

from database import engine, Base, get_db
import models
import schemas

# Create database tables
Base.metadata.create_all(bind=engine)

app = FastAPI(title="envfix Analytics API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

api_key_header = APIKeyHeader(name="X-API-Key")

def get_team_by_api_key(api_key: str = Security(api_key_header), db: Session = Depends(get_db)) -> models.Team:
    team = db.query(models.Team).filter(models.Team.api_key == api_key).first()
    if not team:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    return team

@app.post("/teams", response_model=schemas.TeamResponse)
def create_team(team: schemas.TeamCreate, db: Session = Depends(get_db)):
    """
    Create a new team. Returns the team details including the newly generated API key.
    """
    new_team = models.Team(
        name=team.name,
        api_key=str(uuid.uuid4())
    )
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    return new_team

@app.post("/events", response_model=schemas.EventResponse)
def create_event(
    event: schemas.EventCreate, 
    db: Session = Depends(get_db), 
    team: models.Team = Depends(get_team_by_api_key)
):
    """
    Log a new envfix usage event.
    """
    new_event = models.Event(
        team_id=team.id,
        error_type=event.error_type,
        provider_used=event.provider_used,
        was_cache_hit=event.was_cache_hit,
        fix_applied=event.fix_applied,
        fix_worked=event.fix_worked
    )
    db.add(new_event)
    db.commit()
    db.refresh(new_event)
    return new_event

@app.get("/teams/{team_id}/stats", response_model=schemas.TeamStats)
def get_team_stats(
    team_id: int, 
    db: Session = Depends(get_db), 
    team: models.Team = Depends(get_team_by_api_key)
):
    """
    Get aggregated usage statistics for a team.
    """
    if team.id != team_id:
        raise HTTPException(status_code=403, detail="Not authorized to view stats for this team")

    # Total events
    total_events = db.query(models.Event).filter(models.Event.team_id == team_id).count()

    # Success rate
    applied_events = db.query(models.Event).filter(
        models.Event.team_id == team_id,
        models.Event.fix_applied == True,
        models.Event.fix_worked != None
    ).all()
    
    success_rate = 0.0
    if applied_events:
        worked_count = sum(1 for e in applied_events if e.fix_worked)
        success_rate = (worked_count / len(applied_events)) * 100

    # Most used provider
    provider_counts = db.query(
        models.Event.provider_used, 
        func.count(models.Event.id).label("count")
    ).filter(models.Event.team_id == team_id) \
     .group_by(models.Event.provider_used) \
     .order_by(desc("count")).first()

    most_used_provider = provider_counts[0] if provider_counts else None

    # Error type breakdown
    error_types = db.query(
        models.Event.error_type, 
        func.count(models.Event.id)
    ).filter(models.Event.team_id == team_id) \
     .group_by(models.Event.error_type).all()

    error_type_breakdown = {e[0]: e[1] for e in error_types}

    return schemas.TeamStats(
        total_events=total_events,
        success_rate=success_rate,
        most_used_provider=most_used_provider,
        error_type_breakdown=error_type_breakdown
    )
