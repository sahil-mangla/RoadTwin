"""Response contracts for health, deterioration, forecast and accuracy endpoints."""

import uuid
from datetime import datetime

from pydantic import BaseModel


class HealthRecord(BaseModel):
    id: uuid.UUID
    measured_at: datetime
    health_score: float
    band: str
    deterioration_rate: float | None
    risk_score: float | None
    components: dict | None


class HealthHistory(BaseModel):
    current: HealthRecord | None
    history: list[HealthRecord]


class HistorySummary(BaseModel):
    points: int
    span_days: float
    observation_reports: int


class DeteriorationView(BaseModel):
    """`status` is "insufficient_data" (rate withheld, `reasons` says why) or "ok"."""

    status: str
    rate_per_day: float | None = None
    trend: str | None = None
    reasons: list[str] = []
    history: HistorySummary


class HorizonView(BaseModel):
    horizon_days: int
    predicted_health_score: float
    predicted_band: str
    failure_probability: float | None
    confidence: float | None
    method: str
    explanation: str | None


class ForecastView(BaseModel):
    status: str  # "ok" | "insufficient_data"
    generated_at: datetime | None = None
    horizons: list[HorizonView] = []
    reasons: list[str] = []


class AccuracyRow(BaseModel):
    horizon_days: int
    evaluated: int
    mean_absolute_error: float
    bias: float          # mean(predicted - actual); positive = too optimistic
    rmse: float


class AccuracySummary(BaseModel):
    horizons: list[AccuracyRow]


class SegmentForecast(BaseModel):
    segment_id: uuid.UUID
    health_score: float | None
    band: str | None
    measured_at: datetime | None
    provisional: bool = True
    deterioration: DeteriorationView
    forecast: ForecastView
    accuracy: AccuracySummary


class EvaluationRow(BaseModel):
    segment_id: uuid.UUID
    horizon_days: int
    method: str
    target_at: datetime
    predicted_health_score: float
    actual_health_score: float
    error: float


class ForecastAccuracy(BaseModel):
    overall: AccuracySummary
    recent: list[EvaluationRow]
