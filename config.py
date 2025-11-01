# Configuration file for MGNREGA Analytics Platform

import os
from typing import List

# ============================================
# API Configuration
# ============================================

# data.gov.in API credentials
API_BASE_URL = "https://api.data.gov.in/resource/ee03643a-ee4c-48c2-ac30-9f2ff26ab722"
# API_KEY = "579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b"  # Set via environment variable
API_KEY = os.get("API_KEY","579b464db66ec23bdd000001cdd3946e44ce4aad7209ff7b23ac571b")  # Set via environment variable
API_TIMEOUT = 30  # seconds

# State filter
TARGET_STATE = "TAMIL NADU"

# Batch settings for data fetching
BATCH_SIZE = 500
API_RETRY_ATTEMPTS = 3
API_RETRY_DELAY = 5  # seconds between retries

# ============================================
# Database Configuration
# ============================================

DB_PATH = os.getenv("DB_PATH", "mgnrega.db")
DB_TIMEOUT = 10.0  # seconds

# ============================================
# In-Memory Cache Configuration
# ============================================

# Enable/disable in-memory cache loading
ENABLE_INMEMORY_CACHE = True

# Tables to load into memory (leave empty to load all)
INMEMORY_TABLES = ["analytics_metrics", "mgnrega"]

# ============================================
# FastAPI Configuration
# ============================================

FASTAPI_HOST = "0.0.0.0"
FASTAPI_PORT = 8000
FASTAPI_WORKERS = 4
FASTAPI_RELOAD = True

# ============================================
# Caching Configuration
# ============================================

# Response caching time-to-live in seconds
CACHE_TTL_SECONDS = 300  # 5 minutes

# Max cache entries before eviction (LRU)
CACHE_MAX_ENTRIES = 10000

# ============================================
# Rate Limiting Configuration
# ============================================

# Requests per minute per IP address
RATE_LIMIT_REQUESTS = 60
RATE_LIMIT_WINDOW_SECONDS = 60

# Global request limit (all IPs combined)
GLOBAL_RATE_LIMIT = 10000  # per minute

# ============================================
# Analytics Precomputation Configuration
# ============================================

# Metrics to precompute
METRICS_TO_COMPUTE = [
    "Total_Exp",
    "Wages",
    "Total_Households_Worked",
    "Total_Individuals_Worked",
    "Total_No_of_Active_Workers",
    "Number_of_Completed_Works",
    "Women_Persondays",
    "SC_persondays",
    "ST_persondays",
    "Average_days_of_employment_provided_per_Household",
    "Approved_Labour_Budget"
]

# Aggregation functions to compute
AGGREGATION_FUNCTIONS = ["SUM", "AVG", "MIN", "MAX", "COUNT"]

# Batch precomputation size
PRECOMPUTE_BATCH_SIZE = 1000

# ============================================
# Data Fields Definition
# ============================================

UNIQUE_KEYS = [
    "fin_year", "month", "state_code", "state_name", "district_code", "district_name"
]

FIELDS = [
    {"id": "fin_year", "type": "text"},
    {"id": "month", "type": "text"},
    {"id": "state_code", "type": "keyword"},
    {"id": "state_name", "type": "text"},
    {"id": "district_code", "type": "keyword"},
    {"id": "district_name", "type": "text"},
    {"id": "Approved_Labour_Budget", "type": "long"},
    {"id": "Average_Wage_rate_per_day_per_person", "type": "long"},
    {"id": "Average_days_of_employment_provided_per_Household", "type": "long"},
    {"id": "Differently_abled_persons_worked", "type": "long"},
    {"id": "Material_and_skilled_Wages", "type": "long"},
    {"id": "Number_of_Completed_Works", "type": "long"},
    {"id": "Number_of_GPs_with_NIL_exp", "type": "long"},
    {"id": "Number_of_Ongoing_Works", "type": "long"},
    {"id": "Persondays_of_Central_Liability_so_far", "type": "long"},
    {"id": "SC_persondays", "type": "long"},
    {"id": "SC_workers_against_active_workers", "type": "long"},
    {"id": "ST_persondays", "type": "long"},
    {"id": "ST_workers_against_active_workers", "type": "long"},
    {"id": "Total_Adm_Expenditure", "type": "long"},
    {"id": "Total_Exp", "type": "long"},
    {"id": "Total_Households_Worked", "type": "long"},
    {"id": "Total_Individuals_Worked", "type": "long"},
    {"id": "Total_No_of_Active_Job_Cards", "type": "long"},
    {"id": "Total_No_of_Active_Workers", "type": "long"},
    {"id": "Total_No_of_HHs_completed_100_Days_of_Wage_Employment", "type": "long"},
    {"id": "Total_No_of_JobCards_issued", "type": "long"},
    {"id": "Total_No_of_Workers", "type": "long"},
    {"id": "Total_No_of_Works_Takenup", "type": "long"},
    {"id": "Wages", "type": "long"},
    {"id": "Women_Persondays", "type": "long"},
    {"id": "percent_of_Category_B_Works", "type": "long"},
    {"id": "percent_of_Expenditure_on_Agriculture_Allied_Works", "type": "long"},
    {"id": "percent_of_NRM_Expenditure", "type": "long"},
    {"id": "percentage_payments_gererated_within_15_days", "type": "long"},
    {"id": "Remarks", "type": "text"},
]

# ============================================
# Logging Configuration
# ============================================

LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = "mgnrega_analytics.log"

# ============================================
# Security Configuration
# ============================================

# API key for protected endpoints (optional)
ADMIN_API_KEY = os.getenv("ADMIN_API_KEY", None)

# Enable CORS
ENABLE_CORS = True
CORS_ORIGINS = ["*"]  # Restrict in production

# ============================================
# Performance Tuning
# ============================================

# SQLite WAL mode (Write-Ahead Logging)
SQLITE_WAL_MODE = True

# SQLite cache size in pages
SQLITE_CACHE_SIZE = 10000

# SQLite synchronous mode (0=OFF, 1=NORMAL, 2=FULL)
SQLITE_SYNCHRONOUS = 1

# ============================================
# Deployment Configuration
# ============================================

# Environment: development, staging, production
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")

# Debug mode
DEBUG = ENVIRONMENT == "development"

# Version
API_VERSION = "1.0.0"
