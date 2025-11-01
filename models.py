# Pydantic models for API responses

from pydantic import BaseModel
from typing import List, Dict, Any, Optional
from datetime import datetime

class MetricValue(BaseModel):
    """Single metric value"""
    metric_name: str
    metric_value: Optional[float]
    computed_at: Optional[str]

class DistrictMetrics(BaseModel):
    """Metrics for a single district"""
    district_code: str
    district_name: str
    metrics: Dict[str, Any]

class CrossDistrictResponse(BaseModel):
    """Response for cross-district comparison"""
    fin_year: str
    month: str
    timestamp: str
    total_districts: int
    districts: List[DistrictMetrics]

class MonthlyTrend(BaseModel):
    """Single month's data for trend"""
    fin_year: str
    month: str
    metrics: Dict[str, Any]

class DistrictTrendsResponse(BaseModel):
    """Response for district trends over time"""
    district_code: str
    district_name: str
    timestamp: str
    total_months: int
    trends: List[MonthlyTrend]

class AggregateStats(BaseModel):
    """Aggregate statistics for a district"""
    total_exp: Optional[float]
    avg_exp: Optional[float]
    min_exp: Optional[float]
    max_exp: Optional[float]
    total_households: Optional[float]
    total_individuals: Optional[float]
    total_women_persondays: Optional[float]

class DistrictAggregateResponse(BaseModel):
    """Response for district aggregates"""
    district_code: str
    district_name: str
    timestamp: str
    aggregate: AggregateStats

class HealthStatus(BaseModel):
    """Health check response"""
    status: str
    timestamp: str
    database_size: int
    total_records: int
    cache_enabled: bool
    uptime_seconds: float

class ErrorResponse(BaseModel):
    """Standard error response"""
    error: str
    detail: Optional[str]
    timestamp: str

class RefreshResponse(BaseModel):
    """Response from analytics refresh"""
    status: str
    records_processed: int
    metrics_computed: int
    timestamp: str
