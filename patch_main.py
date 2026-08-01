import sys

with open("envfix-backend/main.py", "r", encoding="utf-8") as f:
    content = f.read()

# Replace event instantiation
target = """    new_event = models.Event(
        team_id=team.id,
        error_type=event.error_type,
        provider_used=event.provider_used,
        was_cache_hit=event.was_cache_hit,
        fix_applied=event.fix_applied,
        fix_worked=event.fix_worked
    )"""

replacement = """    new_event = models.Event(
        team_id=team.id,
        error_type=event.error_type,
        provider_used=event.provider_used,
        was_cache_hit=event.was_cache_hit,
        fix_applied=event.fix_applied,
        fix_worked=event.fix_worked,
        installation_id=event.installation_id,
        redacted_secrets_count=event.redacted_secrets_count
    )"""

content = content.replace(target, replacement)

# Add new endpoints at the end of the file
new_endpoints = """

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
"""

content += new_endpoints

with open("envfix-backend/main.py", "w", encoding="utf-8") as f:
    f.write(content)
