
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, Field


# 1. Input: What the user wants
class UserPreferences(BaseModel):
    request: str
    city: str
    available_minutes: int | None = Field(default=None, gt=0)
    budget_per_person_inr: int | None = Field(default=None, ge=0)
    start_time: datetime | None = None
    group_type: Literal["solo", "partner", "friends"] = "solo"
    group_size: int = Field(default=1, ge=1)
    interests: list[str] = Field(default_factory=list)
    mode: Literal["auto", "activities", "plans"] = "auto"


# 2. Output: A recommended activity
class Activity(BaseModel):
    name: str
    category: str
    description: str
    estimated_cost_inr: float | None = None
    duration_minutes: int
    location: str | None = None
    source_url: str | None = None
    availability: Literal[
        "verified", "unknown", "not_applicable"
    ] = "unknown"
    reason: str


# 3. Output: A multi-activity plan
class ActivityPlan(BaseModel):
    title: str
    activities: list[Activity]
    total_duration_minutes: int
    estimated_cost_inr: float | None = None
    reason: str


# 4. Final response sent to Streamlit
class TimeWiseResponse(BaseModel):
    selected_mode: Literal["activities", "plans"]
    activities: list[Activity] = Field(default_factory=list)
    plans: list[ActivityPlan] = Field(default_factory=list)
    message: str | None = None
