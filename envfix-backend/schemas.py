from pydantic import BaseModel
from typing import Optional
from datetime import datetime

class TeamCreate(BaseModel):
    name: str

class TeamResponse(BaseModel):
    id: int
    name: str
    api_key: str
    created_at: datetime

    class Config:
        from_attributes = True

class EventCreate(BaseModel):
    error_type: str
    provider_used: str
    was_cache_hit: bool
    fix_applied: bool
    fix_worked: Optional[bool] = None

class EventResponse(BaseModel):
    id: int
    team_id: int
    error_type: str
    provider_used: str
    was_cache_hit: bool
    fix_applied: bool
    fix_worked: Optional[bool]
    created_at: datetime

    class Config:
        from_attributes = True

class TeamStats(BaseModel):
    total_events: int
    success_rate: float
    most_used_provider: Optional[str]
    error_type_breakdown: dict[str, int]
