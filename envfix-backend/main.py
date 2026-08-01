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
        avg_manual_fix_minutes=team.avg_manual_fix_minutes,
        hourly_rate=team.hourly_rate,
        api_key=str(uuid.uuid4())
    )
    db.add(new_team)
    db.commit()
    db.refresh(new_team)
    db.refresh(new_team)
    return new_team

@app.patch("/teams/{team_id}", response_model=schemas.TeamResponse)
def update_team(
    team_id: int,
    team_update: schemas.TeamUpdate,
    db: Session = Depends(get_db),
    team: models.Team = Depends(get_team_by_api_key)
):
    """
    Update team settings.
    """
    if team.id != team_id:
        raise HTTPException(status_code=403, detail="Not authorized to update this team")
        
    if team_update.avg_manual_fix_minutes is not None:
        team.avg_manual_fix_minutes = team_update.avg_manual_fix_minutes
    if team_update.hourly_rate is not None:
        team.hourly_rate = team_update.hourly_rate
        
    db.commit()
    db.refresh(team)
    return team

@app.post("/events", response_model=schemas.EventResponse)
def create_event(
    event: schemas.EventCreate, 
    db: Session = Depends(get_db), 
    team: models.Team = Depends(get_team_by_api_key)
):
    """
    Log a new envfix usage event.
    """
    if team.plan == "trial":
        event_count = db.query(models.Event).filter(models.Event.team_id == team.id).count()
        if event_count >= team.trial_events_limit:
            raise HTTPException(status_code=403, detail="Trial limit reached — contact the developer to continue.")

    new_event = models.Event(
        team_id=team.id,
        error_type=event.error_type,
        provider_used=event.provider_used,
        was_cache_hit=event.was_cache_hit,
        fix_applied=event.fix_applied,
        fix_worked=event.fix_worked,
        installation_id=event.installation_id,
        redacted_secrets_count=event.redacted_secrets_count
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

    # Accuracy & Success Rate
    attempted_events = db.query(models.Event).filter(
        models.Event.team_id == team_id,
        models.Event.fix_applied == True
    ).all()
    
    total_fixes_attempted = len(attempted_events)
    total_fixes_successful = sum(1 for e in attempted_events if e.fix_worked == True)
    total_fixes_failed = sum(1 for e in attempted_events if e.fix_worked == False)

    success_rate = None
    if total_fixes_attempted > 0:
        success_rate = (total_fixes_successful / total_fixes_attempted) * 100

    # Recent Failures
    recent_failure_events = db.query(models.Event).filter(
        models.Event.team_id == team_id,
        models.Event.fix_worked == False
    ).order_by(desc(models.Event.created_at)).limit(10).all()
    
    recent_failures = [e.error_type for e in recent_failure_events]

    # Savings Calculation
    resolved_events_count = db.query(models.Event).filter(
        models.Event.team_id == team_id,
        models.Event.fix_applied == True,
        models.Event.fix_worked == True,
        models.Event.was_cache_hit == False
    ).count()

    estimated_hours_saved = (resolved_events_count * team.avg_manual_fix_minutes) / 60.0
    estimated_dollars_saved = estimated_hours_saved * team.hourly_rate

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
        plan=team.plan,
        trial_events_limit=team.trial_events_limit,
        success_rate=success_rate,
        total_fixes_attempted=total_fixes_attempted,
        total_fixes_successful=total_fixes_successful,
        total_fixes_failed=total_fixes_failed,
        recent_failures=recent_failures,
        total_resolved_errors=resolved_events_count,
        estimated_hours_saved=estimated_hours_saved,
        estimated_dollars_saved=estimated_dollars_saved,
        avg_manual_fix_minutes=team.avg_manual_fix_minutes,
        hourly_rate=team.hourly_rate,
        most_used_provider=most_used_provider,
        error_type_breakdown=error_type_breakdown
    )

import time
from fastapi import Request

ip_rate_limits = {}

@app.post("/community/report")
def report_community_fix(report: schemas.CommunityReportCreate, request: Request, db: Session = Depends(get_db)):
    client_ip = request.client.host if request.client else "unknown"
    now = time.time()
    
    if client_ip in ip_rate_limits:
        last_time, count = ip_rate_limits[client_ip]
        if now - last_time < 3600:
            if count > 100:
                raise HTTPException(status_code=429, detail="Rate limit exceeded")
            ip_rate_limits[client_ip] = (last_time, count + 1)
        else:
            ip_rate_limits[client_ip] = (now, 1)
    else:
        ip_rate_limits[client_ip] = (now, 1)

    fix = db.query(models.CommunityFix).filter(
        models.CommunityFix.error_signature == report.signature,
        models.CommunityFix.category == report.category,
        models.CommunityFix.fix_command == report.fix_command
    ).first()
    
    if fix:
        if report.worked:
            fix.success_count += 1
        else:
            fix.failure_count += 1
    else:
        fix = models.CommunityFix(
            error_signature=report.signature,
            category=report.category,
            fix_command=report.fix_command,
            success_count=1 if report.worked else 0,
            failure_count=0 if report.worked else 1
        )
        db.add(fix)
        
    db.commit()
    return {"status": "ok"}

@app.get("/community/lookup", response_model=schemas.CommunityLookupResponse)
def lookup_community_fix(signature: str, category: str, db: Session = Depends(get_db)):
    fixes = db.query(models.CommunityFix).filter(
        models.CommunityFix.error_signature == signature,
        models.CommunityFix.category == category
    ).all()
    
    valid_fixes = [f for f in fixes if (f.success_count + f.failure_count) >= 10]
    if not valid_fixes:
        raise HTTPException(status_code=404, detail="No trusted community fix found")
        
    best_fix = max(valid_fixes, key=lambda f: f.success_count / (f.success_count + f.failure_count))
    success_rate = best_fix.success_count / (best_fix.success_count + best_fix.failure_count)
    
    return schemas.CommunityLookupResponse(
        fix_command=best_fix.fix_command,
        success_rate=success_rate,
        sample_size=best_fix.success_count + best_fix.failure_count
    )


@app.post("/organizations", response_model=schemas.OrganizationResponse)
def create_organization(org: schemas.OrganizationCreate, db: Session = Depends(get_db)):
    new_org = models.Organization(
        name=org.name,
        admin_api_key=str(uuid.uuid4())
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)
    return new_org

@app.put("/organizations/{org_id}/teams/{team_id}")
def associate_team_to_org(org_id: int, team_id: int, db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
        
    team = db.query(models.Team).filter(models.Team.id == team_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
        
    team.org_id = org.id
    db.commit()
    return {"status": "ok"}

@app.post("/doctor_scans")
def create_doctor_scan(scan: schemas.DoctorScanCreate, db: Session = Depends(get_db), team: models.Team = Depends(get_team_by_api_key)):
    new_scan = models.DoctorScan(
        team_id=team.id,
        installation_id=scan.installation_id,
        is_clean=scan.is_clean,
        check_results=scan.check_results
    )
    db.add(new_scan)
    db.commit()
    return {"status": "ok"}

@app.get("/organizations/{org_id}/overview", response_model=schemas.OrganizationOverview)
def get_org_overview(org_id: int, admin_api_key: str = Security(api_key_header), db: Session = Depends(get_db)):
    org = db.query(models.Organization).filter(models.Organization.id == org_id).first()
    if not org or org.admin_api_key != admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid API Key or Organization")

    team_ids = [t.id for t in org.teams]
    if not team_ids:
        return schemas.OrganizationOverview(
            total_machines=0,
            doctor_scan_health={},
            redacted_secrets_count=0,
            estimated_dollars_saved=0.0,
            estimated_hours_saved=0.0,
            team_breakdown=[]
        )

    # Total distinct machines (distinct installation_id across Event and DoctorScan)
    distinct_event_installations = db.query(models.Event.installation_id).filter(
        models.Event.team_id.in_(team_ids), models.Event.installation_id.isnot(None)
    ).distinct().all()
    
    distinct_doctor_installations = db.query(models.DoctorScan.installation_id).filter(
        models.DoctorScan.team_id.in_(team_ids)
    ).distinct().all()

    all_installations = set([r[0] for r in distinct_event_installations] + [r[0] for r in distinct_doctor_installations])
    total_machines = len(all_installations)

    # Doctor scan health
    recent_scans = db.query(models.DoctorScan).filter(
        models.DoctorScan.team_id.in_(team_ids)
    ).order_by(desc(models.DoctorScan.created_at)).limit(100).all()

    scan_stats = {}
    for scan in recent_scans:
        for check in scan.check_results:
            cname = check.get("name")
            if cname not in scan_stats:
                scan_stats[cname] = {"clean": 0, "flagged": 0}
            if check.get("ok"):
                scan_stats[cname]["clean"] += 1
            else:
                scan_stats[cname]["flagged"] += 1

    doctor_scan_health = {}
    for cname, stats in scan_stats.items():
        total = stats["clean"] + stats["flagged"]
        doctor_scan_health[cname] = {
            "clean_pct": (stats["clean"] / total * 100) if total > 0 else 0,
            "flagged_pct": (stats["flagged"] / total * 100) if total > 0 else 0
        }

    # Redacted secrets count
    total_redacted = db.query(func.sum(models.Event.redacted_secrets_count)).filter(
        models.Event.team_id.in_(team_ids)
    ).scalar() or 0

    # Team Breakdown
    team_breakdown = []
    total_org_dollars_saved = 0.0
    total_org_hours_saved = 0.0

    for t in org.teams:
        t_events = db.query(models.Event).filter(models.Event.team_id == t.id).all()
        total_events = len(t_events)
        
        attempted = [e for e in t_events if e.fix_applied]
        total_attempted = len(attempted)
        total_worked = sum(1 for e in attempted if e.fix_worked)
        success_rate = (total_worked / total_attempted * 100) if total_attempted > 0 else None
        
        resolved = [e for e in attempted if e.fix_worked and not e.was_cache_hit]
        hours_saved = len(resolved) * t.avg_manual_fix_minutes / 60.0
        dollars_saved = hours_saved * t.hourly_rate
        
        total_org_dollars_saved += dollars_saved
        total_org_hours_saved += hours_saved

        team_breakdown.append(schemas.TeamSummary(
            id=t.id,
            name=t.name,
            total_events=total_events,
            success_rate=success_rate,
            estimated_dollars_saved=dollars_saved
        ))

    return schemas.OrganizationOverview(
        total_machines=total_machines,
        doctor_scan_health=doctor_scan_health,
        redacted_secrets_count=int(total_redacted),
        estimated_dollars_saved=total_org_dollars_saved,
        estimated_hours_saved=total_org_hours_saved,
        team_breakdown=team_breakdown
    )
