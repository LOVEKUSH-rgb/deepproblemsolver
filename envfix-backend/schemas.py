from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from datetime import datetime

class OrganizationCreate(BaseModel):
    name: str

class OrganizationResponse(BaseModel):
    id: int
    name: str
    admin_api_key: str
    created_at: datetime

    class Config:
        from_attributes = True

class TeamCreate(BaseModel):
    name: str
    avg_manual_fix_minutes: int = 18
    hourly_rate: float = 75.0

class TeamResponse(BaseModel):
    id: int
    name: str
    api_key: str
    avg_manual_fix_minutes: int
    hourly_rate: float
    plan: str
    trial_events_limit: int
    trial_started_at: datetime
    created_at: datetime

    class Config:
        from_attributes = True

class TeamUpdate(BaseModel):
    avg_manual_fix_minutes: Optional[int] = None
    hourly_rate: Optional[float] = None

class EventCreate(BaseModel):
    error_type: str
    provider_used: str
    was_cache_hit: bool
    fix_applied: bool
    fix_worked: Optional[bool] = None
    installation_id: Optional[str] = None
    redacted_secrets_count: int = 0

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
    plan: str
    trial_events_limit: int
    success_rate: Optional[float]
    total_fixes_attempted: int
    total_fixes_successful: int
    total_fixes_failed: int
    recent_failures: list[str]
    total_resolved_errors: int
    estimated_hours_saved: float
    estimated_dollars_saved: float
    avg_manual_fix_minutes: int
    hourly_rate: float
    most_used_provider: Optional[str]
    error_type_breakdown: dict[str, int]

class DoctorScanCreate(BaseModel):
    installation_id: str
    is_clean: bool
    check_results: List[Dict[str, Any]]

class TeamSummary(BaseModel):
    id: int
    name: str
    total_events: int
    success_rate: Optional[float]
    estimated_dollars_saved: float

class OrganizationOverview(BaseModel):
    total_machines: int
    doctor_scan_health: Dict[str, Dict[str, float]] # e.g. {"Python": {"clean_pct": 80.0, "flagged_pct": 20.0}}
    redacted_secrets_count: int
    estimated_dollars_saved: float
    estimated_hours_saved: float
    team_breakdown: List[TeamSummary]

class CommunityReportCreate(BaseModel):
    signature: str
    category: str
    fix_command: str
    worked: bool

class CommunityLookupResponse(BaseModel):
    fix_command: str
    success_rate: float
    sample_size: int
