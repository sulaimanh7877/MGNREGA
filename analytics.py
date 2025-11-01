# Analytics precomputation and aggregation logic

import sqlite3
from contextlib import closing
from datetime import datetime
import logging
from typing import Dict, List, Any, Optional
from database import get_connection
from config import METRICS_TO_COMPUTE, AGGREGATION_FUNCTIONS

logger = logging.getLogger(__name__)

def precompute_cross_district_metrics():
    """Compute metrics grouped by fin_year, month (cross-district comparison)."""
    logger.info("🔄 Precomputing cross-district metrics...")
    
    con = get_connection()
    try:
        # Get unique year-month combinations
        year_months = con.execute("""
            SELECT DISTINCT fin_year, month FROM mgnrega
            ORDER BY fin_year DESC, month DESC
        """).fetchall()
        
        count = 0
        for fin_year, month in year_months:
            for metric in METRICS_TO_COMPUTE:
                try:
                    # Sum metric by district for this year-month
                    districts = con.execute(f"""
                        SELECT district_code, SUM({metric}) as metric_value
                        FROM mgnrega
                        WHERE fin_year=? AND month=?
                        GROUP BY district_code
                    """, (fin_year, month)).fetchall()
                    
                    for dist_code, metric_value in districts:
                        if metric_value is not None:
                            con.execute("""
                                INSERT INTO analytics_metrics 
                                (fin_year, month, state_code, district_code, metric_name, metric_value, computed_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(fin_year, month, state_code, district_code, metric_name) 
                                DO UPDATE SET metric_value=excluded.metric_value, computed_at=excluded.computed_at
                            """, (fin_year, month, None, dist_code, metric, metric_value, datetime.utcnow().isoformat()))
                            count += 1
                except Exception as e:
                    logger.error(f"Error computing {metric} for {fin_year}-{month}: {e}")
        
        con.commit()
        logger.info(f"✅ Precomputed {count} cross-district metrics")
        return count
        
    finally:
        con.close()

def precompute_district_aggregates():
    """Compute aggregate statistics per district."""
    logger.info("🔄 Precomputing district aggregates...")
    
    con = get_connection()
    try:
        districts = con.execute("SELECT DISTINCT district_code FROM mgnrega").fetchall()
        
        count = 0
        for (district_code,) in districts:
            for metric in METRICS_TO_COMPUTE:
                try:
                    # Compute all aggregations for this district-metric
                    for func in AGGREGATION_FUNCTIONS:
                        func_lower = func.lower()
                        result = con.execute(f"""
                            SELECT {func}({metric}) FROM mgnrega
                            WHERE district_code=?
                        """, (district_code,)).fetchone()[0]
                        
                        if result is not None:
                            metric_name = f"{metric}_{func_lower}"
                            con.execute("""
                                INSERT INTO analytics_metrics 
                                (fin_year, month, state_code, district_code, metric_name, metric_value, computed_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                                ON CONFLICT(fin_year, month, state_code, district_code, metric_name) 
                                DO UPDATE SET metric_value=excluded.metric_value, computed_at=excluded.computed_at
                            """, (None, None, None, district_code, metric_name, result, datetime.utcnow().isoformat()))
                            count += 1
                except Exception as e:
                    logger.error(f"Error computing aggregates for {district_code}-{metric}: {e}")
        
        con.commit()
        logger.info(f"✅ Precomputed {count} district aggregate metrics")
        return count
        
    finally:
        con.close()

def get_cross_district_metrics(fin_year: str, month: str) -> Dict[str, Any]:
    """Retrieve precomputed cross-district metrics from cache/db."""
    con = get_connection()
    try:
        metrics = con.execute("""
            SELECT district_code, metric_name, metric_value
            FROM analytics_metrics
            WHERE fin_year=? AND month=?
        """, (fin_year, month)).fetchall()
        
        # Organize by district
        result = {}
        for dist_code, metric_name, metric_value in metrics:
            if dist_code not in result:
                result[dist_code] = {}
            result[dist_code][metric_name] = metric_value
        
        return result
        
    finally:
        con.close()

def get_district_trends(district_code: str) -> List[Dict[str, Any]]:
    """Get trends for a specific district over time."""
    con = get_connection()
    try:
        trends = con.execute("""
            SELECT fin_year, month, metric_name, metric_value
            FROM analytics_metrics
            WHERE district_code=? AND fin_year IS NOT NULL AND month IS NOT NULL
            ORDER BY fin_year DESC, month DESC
        """, (district_code,)).fetchall()
        
        # Organize by year-month
        result = {}
        for fin_year, month, metric_name, metric_value in trends:
            key = f"{fin_year}_{month}"
            if key not in result:
                result[key] = {"fin_year": fin_year, "month": month, "metrics": {}}
            result[key]["metrics"][metric_name] = metric_value
        
        return list(result.values())
        
    finally:
        con.close()

def get_district_aggregates(district_code: str) -> Dict[str, Any]:
    """Get aggregate statistics for a district."""
    con = get_connection()
    try:
        aggregates = con.execute("""
            SELECT metric_name, metric_value
            FROM analytics_metrics
            WHERE district_code=? AND fin_year IS NULL AND month IS NULL
        """, (district_code,)).fetchall()
        
        result = {}
        for metric_name, metric_value in aggregates:
            result[metric_name] = metric_value
        
        return result
        
    finally:
        con.close()

def precompute_all_analytics():
    """Run all precomputation tasks."""
    logger.info("🚀 Starting full analytics precomputation...")
    
    total_count = 0
    start_time = datetime.utcnow()
    
    try:
        count1 = precompute_cross_district_metrics()
        total_count += count1
        
        count2 = precompute_district_aggregates()
        total_count += count2
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"✅ Precomputation complete: {total_count} metrics computed in {elapsed:.2f}s")
        
        return {
            "status": "success",
            "metrics_computed": total_count,
            "duration_seconds": elapsed
        }
        
    except Exception as e:
        logger.error(f"❌ Precomputation failed: {e}")
        raise

def incremental_update_metric(fin_year: Optional[str], month: Optional[str], 
                            district_code: str, metric_name: str, 
                            metric_value: float):
    """Update a single metric incrementally (for live updates)."""
    con = get_connection()
    try:
        con.execute("""
            INSERT INTO analytics_metrics 
            (fin_year, month, state_code, district_code, metric_name, metric_value, computed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(fin_year, month, state_code, district_code, metric_name) 
            DO UPDATE SET metric_value=excluded.metric_value, computed_at=excluded.computed_at
        """, (fin_year, month, None, district_code, metric_name, metric_value, datetime.utcnow().isoformat()))
        con.commit()
        logger.debug(f"Updated: {district_code} {metric_name} = {metric_value}")
        
    finally:
        con.close()

def get_analytics_metadata():
    """Get metadata about precomputed analytics."""
    con = get_connection()
    try:
        total_metrics = con.execute("SELECT COUNT(*) FROM analytics_metrics").fetchone()[0]
        
        last_computed = con.execute("""
            SELECT MAX(computed_at) FROM analytics_metrics
        """).fetchone()[0]
        
        metrics_count = con.execute("""
            SELECT COUNT(DISTINCT metric_name) FROM analytics_metrics
        """).fetchone()[0]
        
        districts_count = con.execute("""
            SELECT COUNT(DISTINCT district_code) FROM analytics_metrics WHERE district_code IS NOT NULL
        """).fetchone()[0]
        
        return {
            "total_metrics": total_metrics,
            "unique_metric_names": metrics_count,
            "unique_districts": districts_count,
            "last_computed": last_computed
        }
        
    finally:
        con.close()
