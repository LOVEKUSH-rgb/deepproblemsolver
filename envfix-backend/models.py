from sqlalchemy import Column, Integer, String, Boolean, DateTime, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from database import Base

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

    events = relationship("Event", back_populates="team")

class Event(Base):
    __tablename__ = "events"

    id = Column(Integer, primary_key=True, index=True)
    team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    error_type = Column(String, nullable=False)
    provider_used = Column(String, nullable=False)
    was_cache_hit = Column(Boolean, nullable=False, default=False)
    fix_applied = Column(Boolean, nullable=False, default=False)
    fix_worked = Column(Boolean, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    team = relationship("Team", back_populates="events")
