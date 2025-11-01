import logging
import sqlite3
import os
from datetime import datetime, timedelta
from io import StringIO
from typing import Optional

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

import config
from database import get_connection, init_db, get_record_count, vacuum_db
from cache import init_cache, get_cache, cache_key, invalidate_cache_pattern
from models import (
    CrossDistrictResponse, DistrictTrendsResponse, DistrictAggregateResponse,
    HealthStatus, ErrorResponse, RefreshResponse, DistrictMetrics, MonthlyTrend, AggregateStats
)
from analytics import (
    get_cross_district_metrics, get_district_trends, get_district_aggregates,
    precompute_all_analytics, get_analytics_metadata
)

# Setup logging
logging.basicConfig(
    level=config.LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="MGNREGA Analytics API",
    description="Analytics API for MGNREGA data with precomputed metrics",
    version=config.API_VERSION
)

# Setup CORS
if config.ENABLE_CORS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Setup rate limiting
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content={"error": "Too Many Requests", "detail": str(exc.detail)},
    )

# Global state
app.state.start_time = datetime.utcnow()
app.state.memcon = None

# ============================================
# Startup and Shutdown Events
# ============================================

@app.on_event("startup")
async def startup():
    """Initialize database and cache on startup."""
    logger.info("🚀 Starting up MGNREGA Analytics API...")
    
    try:
        # Initialize database
        init_db()
        logger.info("✅ Database initialized")
        
        # Initialize cache
        init_cache(
            max_entries=config.CACHE_MAX_ENTRIES,
            ttl_seconds=config.CACHE_TTL_SECONDS
        )
        logger.info(f"✅ Cache initialized (TTL: {config.CACHE_TTL_SECONDS}s)")
        
        # Load database into memory for fast queries
        if config.ENABLE_INMEMORY_CACHE:
            load_db_to_memory()
            logger.info("✅ Database loaded into memory")
        
        logger.info("✅ Startup complete")
        
    except Exception as e:
        logger.error(f"❌ Startup failed: {e}", exc_info=True)
        raise

@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    logger.info("👋 Shutting down...")
    if app.state.memcon:
        app.state.memcon.close()
    logger.info("✅ Shutdown complete")

# ============================================
# Utility Functions
# ============================================

def load_db_to_memory():
    """Load SQLite database into memory for faster queries."""
    try:
        disk_conn = get_connection(config.DB_PATH)
        disk_conn.row_factory = sqlite3.Row
        
        # Dump disk database
        temp = StringIO()
        for line in disk_conn.iterdump():
            temp.write(f"{line}\n")
        disk_conn.close()
        
        # Load into memory
        temp.seek(0)
        mem_conn = sqlite3.connect(":memory:")
        mem_conn.row_factory = sqlite3.Row
        mem_conn.executescript(temp.read())
        mem_conn.commit()
        
        app.state.memcon = mem_conn
        logger.info("✅ Loaded database to memory")
        
    except Exception as e:
        logger.error(f"Failed to load DB to memory: {e}, falling back to disk", exc_info=True)
        app.state.memcon = None

def get_db():
    """Get database connection (memory if available, else disk). Always has row_factory set."""
    if app.state.memcon:
        return app.state.memcon
    con = get_connection()
    con.row_factory = sqlite3.Row
    return con

# ============================================
# API Endpoints
# ============================================

@app.get("/")
async def root():
    """Root endpoint with API info."""
    return {
        "name": "MGNREGA Analytics API",
        "version": config.API_VERSION,
        "docs": "/docs",
        "openapi_url": "/openapi.json"
    }

@app.get("/dashboard")
async def dashboard():
    """Serve the MGNREGA district dashboard."""
    return FileResponse("dashboard.html", media_type="text/html")

@app.get("/health", response_model=HealthStatus)
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def health(request: Request):
    """Health check endpoint."""
    try:
        db_size = os.path.getsize(config.DB_PATH) if os.path.exists(config.DB_PATH) else 0
        total_records = get_record_count()
        uptime = (datetime.utcnow() - app.state.start_time).total_seconds()
        
        return HealthStatus(
            status="healthy",
            timestamp=datetime.utcnow().isoformat(),
            database_size=db_size,
            total_records=total_records,
            cache_enabled=config.ENABLE_INMEMORY_CACHE,
            uptime_seconds=uptime
        )
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/cross-district/{fin_year}/{month}", response_model=CrossDistrictResponse)
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def cross_district_metrics(request: Request, fin_year: str, month: str):
    """Get metrics comparing across districts for a specific financial year and month."""
    try:
        cache_key_str = cache_key("cross_district", fin_year, month)
        cached_result = get_cache().get(cache_key_str)
        if cached_result:
            logger.debug(f"Cache hit: {cache_key_str}")
            return cached_result
        
        metrics_by_district = get_cross_district_metrics(fin_year, month)
        
        districts = []
        con = get_db()
        for dist_code, metrics in metrics_by_district.items():
            dist_name_row = con.execute(
                "SELECT DISTINCT district_name FROM mgnrega WHERE district_code=? LIMIT 1",
                (dist_code,)
            ).fetchone()
            dist_name = dict(dist_name_row)["district_name"] if dist_name_row else f"District {dist_code}"
            
            districts.append(DistrictMetrics(
                district_code=dist_code,
                district_name=dist_name,
                metrics=metrics
            ))
        
        response = CrossDistrictResponse(
            fin_year=fin_year,
            month=month,
            timestamp=datetime.utcnow().isoformat(),
            total_districts=len(districts),
            districts=districts
        )
        
        get_cache().set(cache_key_str, response)
        return response
        
    except Exception as e:
        logger.error(f"Error fetching cross-district metrics: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/district/{district_code}/trends", response_model=DistrictTrendsResponse)
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def district_trends(request: Request, district_code: str):
    """Get monthly trends for a specific district."""
    try:
        cache_key_str = cache_key("district_trends", district_code)
        cached_result = get_cache().get(cache_key_str)
        if cached_result:
            logger.debug(f"Cache hit: {cache_key_str}")
            return cached_result
        
        con = get_db()
        dist_name_row = con.execute(
            "SELECT DISTINCT district_name FROM mgnrega WHERE district_code=? LIMIT 1",
            (district_code,)
        ).fetchone()
        dist_name = dict(dist_name_row)["district_name"] if dist_name_row else f"District {district_code}"
        
        trends_data = get_district_trends(district_code)
        
        trends = [
            MonthlyTrend(
                fin_year=t["fin_year"],
                month=t["month"],
                metrics=t["metrics"]
            )
            for t in trends_data
        ]
        
        response = DistrictTrendsResponse(
            district_code=district_code,
            district_name=dist_name,
            timestamp=datetime.utcnow().isoformat(),
            total_months=len(trends),
            trends=trends
        )
        
        get_cache().set(cache_key_str, response)
        return response
        
    except Exception as e:
        logger.error(f"Error fetching district trends: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/metrics/district/{district_code}/aggregate", response_model=DistrictAggregateResponse)
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def district_aggregate(request: Request, district_code: str):
    """Get aggregate statistics for a district."""
    try:
        cache_key_str = cache_key("district_aggregate", district_code)
        cached_result = get_cache().get(cache_key_str)
        if cached_result:
            logger.debug(f"Cache hit: {cache_key_str}")
            return cached_result
        
        con = get_db()
        dist_name_row = con.execute(
            "SELECT DISTINCT district_name FROM mgnrega WHERE district_code=? LIMIT 1",
            (district_code,)
        ).fetchone()
        dist_name = dict(dist_name_row)["district_name"] if dist_name_row else f"District {district_code}"
        
        agg_data = get_district_aggregates(district_code)
        
        aggregate = AggregateStats(
            total_exp=agg_data.get("Total_Exp_sum"),
            avg_exp=agg_data.get("Total_Exp_avg"),
            min_exp=agg_data.get("Total_Exp_min"),
            max_exp=agg_data.get("Total_Exp_max"),
            total_households=agg_data.get("Total_Households_Worked_sum"),
            total_individuals=agg_data.get("Total_Individuals_Worked_sum"),
            total_women_persondays=agg_data.get("Women_Persondays_sum")
        )
        
        response = DistrictAggregateResponse(
            district_code=district_code,
            district_name=dist_name,
            timestamp=datetime.utcnow().isoformat(),
            aggregate=aggregate
        )
        
        get_cache().set(cache_key_str, response)
        return response
        
    except Exception as e:
        logger.error(f"Error fetching district aggregates: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/refresh-analytics", response_model=RefreshResponse)
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def refresh_analytics(request: Request):
    """Manually trigger analytics precomputation and invalidate cache."""
    try:
        logger.info("🔄 Manual analytics refresh triggered")
        
        result = precompute_all_analytics()
        
        invalidate_cache_pattern("cross_district")
        invalidate_cache_pattern("district_trends")
        invalidate_cache_pattern("district_aggregate")
        
        return RefreshResponse(
            status="success",
            records_processed=get_record_count(),
            metrics_computed=result.get("metrics_computed", 0),
            timestamp=datetime.utcnow().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Analytics refresh failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics-metadata")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def analytics_metadata(request: Request):
    """Get metadata about precomputed analytics."""
    try:
        metadata = get_analytics_metadata()
        cache_stats = get_cache().get_stats()
        
        return {
            "analytics": metadata,
            "cache": cache_stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting metadata: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/cache-stats")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def cache_stats(request: Request):
    """Get cache statistics."""
    try:
        stats = get_cache().get_stats()
        return {
            "cache": stats,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error getting cache stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/optimize-database")
@limiter.limit("5/minute")
async def optimize_database(request: Request):
    """Optimize database (vacuum and reindex)."""
    try:
        logger.info("🔧 Database optimization triggered")
        vacuum_db()
        
        return {
            "status": "success",
            "message": "Database optimized",
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Database optimization failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

# ============================================
# Dashboard Support Endpoints
# ============================================

@app.get("/districts")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def get_all_districts(request: Request):
    """Get list of all available districts."""
    try:
        con = get_db()
        districts = con.execute("""
            SELECT DISTINCT district_code, district_name, state_name
            FROM mgnrega
            ORDER BY district_name
        """).fetchall()
        
        result = [
            {
                "code": dict(row)["district_code"],
                "name": dict(row)["district_name"],
                "state": dict(row)["state_name"]
            }
            for row in districts
        ]
        
        return {
            "status": "success",
            "total": len(result),
            "districts": result,
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching districts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district-info/{district_code}")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def get_district_info(request: Request, district_code: str):
    """Get complete information about a district."""
    try:
        con = get_db()
        info = con.execute("""
            SELECT DISTINCT district_code, district_name, state_name
            FROM mgnrega
            WHERE district_code = ?
            LIMIT 1
        """, (district_code,)).fetchone()
        
        if not info:
            raise HTTPException(status_code=404, detail="District not found")
        
        info = dict(info)
        return {
            "code": info["district_code"],
            "name": info["district_name"],
            "state": info["state_name"],
            "timestamp": datetime.utcnow().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error fetching district info: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district-current-year/{district_code}")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def get_district_current_year(request: Request, district_code: str):
    """Get current year performance for a district."""
    try:
        cache_key_str = cache_key("district_current_year", district_code)
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        
        current_year_row = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega
            ORDER BY fin_year DESC LIMIT 1
        """).fetchone()
        
        if not current_year_row:
            return {
                "status": "no_data",
                "message": "No data available",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        fin_year = dict(current_year_row)["fin_year"]
        
        data = con.execute("""
            SELECT 
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as total_individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as total_households,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                SUM(CAST(Number_of_Completed_Works AS FLOAT)) as works_completed,
                SUM(CAST(Total_Exp AS FLOAT)) as total_exp
            FROM mgnrega
            WHERE district_code = ? AND fin_year = ?
        """, (district_code, fin_year)).fetchone()
        
        if not data:
            return {
                "status": "no_data",
                "message": "No data for this district",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        data = dict(data)
        result = {
            "fin_year": fin_year,
            "district_code": district_code,
            "metrics": {
                "total_individuals_worked": data.get("total_individuals", 0) or 0,
                "total_households_worked": data.get("total_households", 0) or 0,
                "total_wages": (data.get("total_wages", 0) or 0) ,
                "works_completed": data.get("works_completed", 0) or 0,
                "total_expenditure": (data.get("total_exp", 0) or 0) 
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        
        get_cache().set(cache_key_str, result)
        return result
        
    except Exception as e:
        logger.error(f"Error fetching current year data: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district-top-performers")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def get_top_performers(request: Request):
    """Get top 5 performing districts."""
    try:
        cache_key_str = cache_key("top_performers")
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        
        current_year_row = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega
            ORDER BY fin_year DESC LIMIT 1
        """).fetchone()
        
        if not current_year_row:
            return {"top_performers": []}
        
        current_year = dict(current_year_row)["fin_year"]
        
        top = con.execute("""
            SELECT 
                district_code,
                district_name,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households
            FROM mgnrega
            WHERE fin_year = ?
            GROUP BY district_code, district_name
            ORDER BY total_wages DESC
            LIMIT 5
        """, (current_year,)).fetchall()
        
        result = {
            "fin_year": current_year,
            "top_performers": [
                {
                    "code": dict(row)["district_code"],
                    "name": dict(row)["district_name"],
                    "wages": (dict(row)["total_wages"] or 0) ,
                    "individuals": dict(row)["individuals"] or 0,
                    "households": dict(row)["households"] or 0
                }
                for row in top
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        get_cache().set(cache_key_str, result, ttl_seconds=3600)
        return result
        
    except Exception as e:
        logger.error(f"Error fetching top performers: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compare-with-top/{district_code}")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def compare_with_top(request: Request, district_code: str):
    """Compare a district with top performers."""
    try:
        cache_key_str = cache_key("compare_top", district_code)
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        
        current_year_row = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega
            ORDER BY fin_year DESC LIMIT 1
        """).fetchone()
        
        if not current_year_row:
            return {"status": "no_data"}
        
        current_year = dict(current_year_row)["fin_year"]
        
        district_data = con.execute("""
            SELECT 
                district_name,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households
            FROM mgnrega
            WHERE district_code = ? AND fin_year = ?
            GROUP BY district_code, district_name
        """, (district_code, current_year)).fetchone()
        
        if not district_data:
            return {
                "status": "no_data",
                "message": "District not found",
                "timestamp": datetime.utcnow().isoformat()
            }
        
        district_data = dict(district_data)
        
        top = con.execute("""
            SELECT 
                district_code,
                district_name,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households
            FROM mgnrega
            WHERE fin_year = ?
            GROUP BY district_code, district_name
            ORDER BY total_wages DESC
            LIMIT 5
        """, (current_year,)).fetchall()
        
        result = {
            "fin_year": current_year,
            "this_district": {
                "code": district_code,
                "name": district_data["district_name"],
                "wages": (district_data["total_wages"] or 0) ,
                "individuals": district_data["individuals"] or 0,
                "households": district_data["households"] or 0
            },
            "top_5": [
                {
                    "code": dict(row)["district_code"],
                    "name": dict(row)["district_name"],
                    "wages": (dict(row)["total_wages"] or 0) ,
                    "individuals": dict(row)["individuals"] or 0,
                    "households": dict(row)["households"] or 0
                }
                for row in top
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        
        get_cache().set(cache_key_str, result, ttl_seconds=3600)
        return result
        
    except Exception as e:
        logger.error(f"Error comparing with top: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district/{district_code}/performance-summary")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def district_performance_summary(request: Request, district_code: str):
    """Get CACHED performance summary with all years."""
    try:
        cache_key_str = cache_key("perf_summary", district_code)
        cached = get_cache().get(cache_key_str)
        if cached:
            logger.debug(f"Cache HIT for perf_summary/{district_code}")
            return cached
        
        con = get_db()
        years = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega 
            WHERE district_code = ? 
            ORDER BY fin_year DESC
        """, (district_code,)).fetchall()
        years = [dict(y) for y in years]

        if not years:
            return {"status": "no_data", "district_code": district_code}
        
        dist_info = con.execute("""
            SELECT DISTINCT district_name, state_name FROM mgnrega
            WHERE district_code = ? LIMIT 1
        """, (district_code,)).fetchone()
        dist_name = dict(dist_info)["district_name"] if dist_info else f"District {district_code}"
        
        yearly_data = []
        for year_row in years:
            year = year_row["fin_year"]
            metrics = con.execute("""
                SELECT
                    SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                    SUM(CAST(Total_Households_Worked AS FLOAT)) as households,
                    SUM(CAST(Wages AS FLOAT)) as wages,
                    SUM(CAST(Number_of_Completed_Works AS FLOAT)) as works,
                    SUM(CAST(Total_Exp AS FLOAT)) as expenditure,
                    SUM(CAST(Women_Persondays AS FLOAT)) as women_days,
                    COUNT(DISTINCT month) as months
                FROM mgnrega
                WHERE district_code = ? AND fin_year = ?
            """, (district_code, year)).fetchone()
            m = dict(metrics) if metrics else {}
            yearly_data.append({
                "fin_year": year,
                "individuals": m.get("individuals", 0) or 0,
                "households": m.get("households", 0) or 0,
                "wages": (m.get("wages", 0) or 0) ,
                "works": m.get("works", 0) or 0,
                "expenditure": (m.get("expenditure", 0) or 0) ,
                "women_persondays": m.get("women_days", 0) or 0,
                "months_active": m.get("months", 0) or 0
            })
        
        result = {
            "district_code": district_code,
            "district_name": dist_name,
            "yearly_performance": yearly_data,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        get_cache().set(cache_key_str, result, ttl_seconds=7200)
        return result
        
    except Exception as e:
        logger.error(f"Error in district summary: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district/{district_code}/year-over-year")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def district_year_over_year(request: Request, district_code: str):
    """Get year-over-year comparison (current year vs previous year)."""
    try:
        cache_key_str = cache_key("yoy", district_code)
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        years = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega
            WHERE district_code = ?
            ORDER BY fin_year DESC LIMIT 2
        """, (district_code,)).fetchall()
        years = [dict(y) for y in years]

        if len(years) < 2:
            return {"status": "insufficient_data", "years_available": len(years)}
        
        current = years[0]["fin_year"]
        previous = years[1]["fin_year"]
        
        current_metrics = con.execute("""
            SELECT
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households,
                SUM(CAST(Wages AS FLOAT)) as wages
            FROM mgnrega
            WHERE district_code = ? AND fin_year = ?
        """, (district_code, current)).fetchone()
        previous_metrics = con.execute("""
            SELECT
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households,
                SUM(CAST(Wages AS FLOAT)) as wages
            FROM mgnrega
            WHERE district_code = ? AND fin_year = ?
        """, (district_code, previous)).fetchone()
        curr = dict(current_metrics) if current_metrics else {}
        prev = dict(previous_metrics) if previous_metrics else {}
        
        def growth(curr_val, prev_val):
            if not prev_val or prev_val == 0:
                return 0 if curr_val == 0 else 100
            return ((curr_val - prev_val) / prev_val) * 100
        
        result = {
            "current_year": current,
            "previous_year": previous,
            "comparison": {
                "individuals": {
                    "current": curr.get("individuals", 0) or 0,
                    "previous": prev.get("individuals", 0) or 0,
                    "growth_percent": growth(curr.get("individuals", 0), prev.get("individuals", 0))
                },
                "households": {
                    "current": curr.get("households", 0) or 0,
                    "previous": prev.get("households", 0) or 0,
                    "growth_percent": growth(curr.get("households", 0), prev.get("households", 0))
                },
                "wages": {
                    "current": (curr.get("wages", 0) or 0) ,
                    "previous": (prev.get("wages", 0) or 0) ,
                    "growth_percent": growth(curr.get("wages", 0), prev.get("wages", 0))
                }
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        get_cache().set(cache_key_str, result, ttl_seconds=7200)
        return result
        
    except Exception as e:
        logger.error(f"Error in YoY: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/compare-districts/{district_code_1}/{district_code_2}")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def compare_two_districts(request: Request, district_code_1: str, district_code_2: str):
    """Compare any 2 districts directly (FAST - cached)."""
    try:
        codes = sorted([district_code_1, district_code_2])
        cache_key_str = cache_key("compare_two", codes[0], codes[1])
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        current_year_row = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega ORDER BY fin_year DESC LIMIT 1
        """).fetchone()
        if not current_year_row:
            return {"status": "no_data"}
        current_year = dict(current_year_row)["fin_year"]
        
        def get_dist_data(code):
            name_row = con.execute("""
                SELECT DISTINCT district_name FROM mgnrega WHERE district_code = ? LIMIT 1
            """, (code,)).fetchone()
            name = dict(name_row)["district_name"] if name_row else f"District {code}"
            metrics = con.execute("""
                SELECT
                    SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                    SUM(CAST(Total_Households_Worked AS FLOAT)) as households,
                    SUM(CAST(Wages AS FLOAT)) as wages,
                    SUM(CAST(Number_of_Completed_Works AS FLOAT)) as works
                FROM mgnrega
                WHERE district_code = ? AND fin_year = ?
            """, (code, current_year)).fetchone()
            m = dict(metrics) if metrics else {}
            return {
                "code": code,
                "name": name,
                "individuals": m.get("individuals", 0) or 0,
                "households": m.get("households", 0) or 0,
                "wages": (m.get("wages", 0) or 0) ,
                "works": m.get("works", 0) or 0
            }
        
        dist1 = get_dist_data(district_code_1)
        dist2 = get_dist_data(district_code_2)
        
        result = {
            "fin_year": current_year,
            "district_1": dist1,
            "district_2": dist2,
            "difference": {
                "individuals": dist1["individuals"] - dist2["individuals"],
                "households": dist1["households"] - dist2["households"],
                "wages": dist1["wages"] - dist2["wages"],
                "works": dist1["works"] - dist2["works"]
            },
            "timestamp": datetime.utcnow().isoformat()
        }
        get_cache().set(cache_key_str, result, ttl_seconds=7200)
        return result
        
    except Exception as e:
        logger.error(f"Error comparing districts: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district-rankings")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def get_district_rankings(request: Request):
    """Get all districts ranked by current year performance (CACHED)."""
    try:
        cache_key_str = cache_key("rankings")
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        current_year_row = con.execute("""
            SELECT DISTINCT fin_year FROM mgnrega ORDER BY fin_year DESC LIMIT 1
        """).fetchone()
        if not current_year_row:
            return {"rankings": []}
        current_year = dict(current_year_row)["fin_year"]
        
        rankings = con.execute("""
            SELECT
                district_code,
                district_name,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households
            FROM mgnrega
            WHERE fin_year = ?
            GROUP BY district_code, district_name
            ORDER BY total_wages DESC
        """, (current_year,)).fetchall()
        rankings = [dict(r) for r in rankings]
        
        result = {
            "fin_year": current_year,
            "rankings": [
                {
                    "rank": idx + 1,
                    "code": row["district_code"],
                    "name": row["district_name"],
                    "wages": (row["total_wages"] or 0) ,
                    "individuals": row["individuals"] or 0,
                    "households": row["households"] or 0
                }
                for idx, row in enumerate(rankings)
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        get_cache().set(cache_key_str, result, ttl_seconds=7200)
        return result
        
    except Exception as e:
        logger.error(f"Error getting rankings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/district/{district_code}/monthly-breakdown/{fin_year}")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def monthly_breakdown(request: Request, district_code: str, fin_year: str):
    """Get month-by-month data for a specific year (no lag)."""
    try:
        cache_key_str = cache_key("monthly", district_code, fin_year)
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        months_data = con.execute("""
            SELECT
                month,
                SUM(CAST(Wages AS FLOAT)) as wages,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as individuals,
                SUM(CAST(Total_Households_Worked AS FLOAT)) as households,
                SUM(CAST(Total_Exp AS FLOAT)) as expenditure
            FROM mgnrega
            WHERE district_code = ? AND fin_year = ?
            GROUP BY month
            ORDER BY 
                CASE month
                    WHEN 'April' THEN 1 WHEN 'May' THEN 2 WHEN 'June' THEN 3
                    WHEN 'July' THEN 4 WHEN 'August' THEN 5 WHEN 'September' THEN 6
                    WHEN 'October' THEN 7 WHEN 'November' THEN 8 WHEN 'December' THEN 9
                    WHEN 'January' THEN 10 WHEN 'February' THEN 11 WHEN 'March' THEN 12
                    ELSE 13 END
        """, (district_code, fin_year)).fetchall()
        months_data = [dict(row) for row in months_data]
        
        result = {
            "fin_year": fin_year,
            "district_code": district_code,
            "monthly_data": [
                {
                    "month": row["month"],
                    "wages": (row["wages"] or 0) ,
                    "individuals": row["individuals"] or 0,
                    "households": row["households"] or 0,
                    "expenditure": (row["expenditure"] or 0) 
                }
                for row in months_data
            ],
            "timestamp": datetime.utcnow().isoformat()
        }
        get_cache().set(cache_key_str, result, ttl_seconds=3600)
        return result
        
    except Exception as e:
        logger.error(f"Error in monthly breakdown: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/analytics/quick-stats")
@limiter.limit(f"{config.RATE_LIMIT_REQUESTS}/minute")
async def quick_stats(request: Request):
    """Get overall state stats (cached)."""
    try:
        cache_key_str = cache_key("quick_stats")
        cached = get_cache().get(cache_key_str)
        if cached:
            return cached
        
        con = get_db()
        stats = con.execute("""
            SELECT
                COUNT(DISTINCT district_code) as total_districts,
                SUM(CAST(Total_Individuals_Worked AS FLOAT)) as total_individuals,
                SUM(CAST(Wages AS FLOAT)) as total_wages,
                COUNT(DISTINCT fin_year) as years_in_data,
                MAX(fin_year) as latest_year
            FROM mgnrega
        """).fetchone()
        s = dict(stats) if stats else {}
        result = {
            "total_districts": s.get("total_districts", 0) or 0,
            "total_individuals_employed": s.get("total_individuals", 0) or 0,
            "total_wages_disbursed": (s.get("total_wages", 0) or 0) ,
            "years_tracked": s.get("years_in_data", 0) or 0,
            "latest_year": s.get("latest_year", "N/A"),
            "timestamp": datetime.utcnow().isoformat()
        }
        get_cache().set(cache_key_str, result, ttl_seconds=7200)
        return result
        
    except Exception as e:
        logger.error(f"Error in quick stats: {e}")
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=config.FASTAPI_HOST,
        port=config.FASTAPI_PORT,
        workers=1 if config.DEBUG else config.FASTAPI_WORKERS
    )
