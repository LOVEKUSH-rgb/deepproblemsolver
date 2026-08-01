from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

class Organization(Base):
    __tablename__ = "organizations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    admin_api_key = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    teams = relationship("Team", back_populates="organization")

class Team(Base):
    __tablename__ = "teams"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    api_key = Column(String, unique=True, index=True, nullable=False)
    avg_manual_fix_minutes = Column(Integer, nullable=False, default=18)
    hourly_rate = Column(Integer, nullable=False, default=75)
    plan = Column(String, nullable=False, default="trial")
    trial_events_limit = Column(Integer, nullable=False, default=100)
    trial_started_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    org_id = Column(Integer, ForeignKey("organizations.id"), nullable=True)

    organization = relationship("Organization", back_populates="teams")
    events = relationship("Event", back_populates="team")
    doctor_scans = relationship("DoctorScan", back_populates="team")

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    error_type = Column(String, nullable=False)
    provider_used = Column(String, nullable=False)
    was_cache_hit = Column(Boolean, nullable=False, default=False)
    fix_applied = Column(Boolean, nullable=False, default=False)
    fix_worked = Column(Boolean, nullable=True)
    installation_id = Column(String, nullable=True)
    redacted_secrets_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="events")

class DoctorScan(Base):
    __tablename__ = "doctor_scans"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    installation_id = Column(String, nullable=False)
    is_clean = Column(Boolean, nullable=False)
    check_results = Column(JSON, nullable=False) # e.g. [{"name": "Python", "ok": True}, ...]
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="doctor_scans")

class CommunityFix(Base):
    __tablename__ = "community_fixes"

    id = Column(Integer, primary_key=True, index=True)
    error_signature = Column(String, index=True, nullable=False)
    category = Column(String, index=True, nullable=False)
    fix_command = Column(String, nullable=False)
    success_count = Column(Integer, default=0, nullable=False)
    failure_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
