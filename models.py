from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime
from sqlalchemy.sql import func
from database import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, unique=True, index=True, nullable=False)
    school_name = Column(String)
    arrival_date = Column(String)
    location = Column(String)
    japanese_level = Column(String)
    has_residence_card = Column(Boolean, default=True)
    housing_type = Column(String, default="dorm")  # dorm | rental | housing_tbd
    school_type = Column(String, default="language_school")  # language_school | university | vocational | high_school
    part_time_plan = Column(String, default="no")   # yes | no | later
    sim_at_airport = Column(Boolean, default=False)
    already_exchanged = Column(Boolean, default=False)
    permit_obtained = Column(Boolean, default=False)  # Work permit obtained (part-time work authorization)
    gemini_api_key = Column(String, nullable=True)
    google_maps_api_key = Column(String, nullable=True)
    ai_roadmap = Column(String, nullable=True)  # JSON: cached AI-generated roadmap overlay
    ai_roadmap_lang = Column(String, nullable=True)  # lang the overlay was generated for
    created_at = Column(DateTime(timezone=True), server_default=func.now())

class Task(Base):
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    task_id = Column(String, nullable=False) # e.g. "task_address", "task_insurance"
    status = Column(String, default="pending") # "pending", "completed"
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class LocationLog(Base):
    __tablename__ = "location_logs"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False)
    latitude = Column(Float)
    longitude = Column(Float)
    address = Column(String)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

class AgentDecision(Base):
    __tablename__ = "agent_decisions"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(String, index=True, nullable=False, unique=True)
    decision_data = Column(String, nullable=False) # JSON serialized string
    created_at = Column(DateTime(timezone=True), server_default=func.now())
