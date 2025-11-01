"""
Scheduled task runner for periodic analytics refresh using APScheduler.
Run this in production to keep analytics fresh without manual intervention.

Usage:
    python scheduler.py
"""

import logging
import time
from datetime import datetime
from apscheduler.schedulers.background import BackgroundScheduler
from data_fetcher import fetch_and_upsert_all
from analytics import precompute_all_analytics
from cache import get_cache, invalidate_cache_pattern
from database import vacuum_db, get_record_count

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('scheduler.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def refresh_data_job():
    """Background job: Fetch and upsert latest data."""
    logger.info("🔄 [SCHEDULER] Starting data refresh job...")
    try:
        result = fetch_and_upsert_all(force_full_sync=False)
        logger.info(f"✅ [SCHEDULER] Data refresh complete: {result}")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Data refresh failed: {e}", exc_info=True)

def refresh_analytics_job():
    """Background job: Precompute analytics and refresh cache."""
    logger.info("⚡ [SCHEDULER] Starting analytics refresh job...")
    try:
        result = precompute_all_analytics()
        logger.info(f"✅ [SCHEDULER] Analytics refresh complete: {result}")
        
        # Invalidate caches
        for pattern in ["cross_district", "district_trends", "district_aggregate"]:
            invalidate_cache_pattern(pattern)
        
        logger.info("🗑️ [SCHEDULER] Cache invalidated")
        
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Analytics refresh failed: {e}", exc_info=True)

def optimize_db_job():
    """Background job: Optimize database."""
    logger.info("🔧 [SCHEDULER] Starting database optimization...")
    try:
        vacuum_db()
        logger.info("✅ [SCHEDULER] Database optimization complete")
    except Exception as e:
        logger.error(f"❌ [SCHEDULER] Database optimization failed: {e}", exc_info=True)

def print_stats_job():
    """Background job: Print system statistics."""
    try:
        cache_stats = get_cache().get_stats()
        record_count = get_record_count()
        logger.info(f"📊 [STATS] Records: {record_count}, Cache: {cache_stats}")
    except Exception as e:
        logger.warning(f"⚠️ [STATS] Could not fetch stats: {e}")

def main():
    """Setup and start scheduler."""
    logger.info("=" * 60)
    logger.info("MGNREGA Analytics Scheduler")
    logger.info("=" * 60)
    
    # Create scheduler
    scheduler = BackgroundScheduler()
    
    # Add jobs
    # Fetch data every 6 hours (2 AM, 8 AM, 2 PM, 8 PM)
    scheduler.add_job(refresh_data_job, 'cron', hour='0,6,12,18', minute=0)
    logger.info("📅 Scheduled: Data refresh at 0:00, 6:00, 12:00, 18:00")
    
    # Precompute analytics every 12 hours (3 AM, 3 PM)
    scheduler.add_job(refresh_analytics_job, 'cron', hour='3,15', minute=0)
    logger.info("📅 Scheduled: Analytics refresh at 3:00 AM, 3:00 PM")
    
    # Optimize database weekly (Sunday at 4 AM)
    scheduler.add_job(optimize_db_job, 'cron', day_of_week='sun', hour=4, minute=0)
    logger.info("📅 Scheduled: Database optimization every Sunday at 4:00 AM")
    
    # Print stats every hour
    scheduler.add_job(print_stats_job, 'interval', hours=1)
    logger.info("📅 Scheduled: Statistics every hour")
    
    # Start scheduler
    scheduler.start()
    logger.info("✅ Scheduler started")
    logger.info("=" * 60)
    
    # Keep scheduler running
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("⏹️  Shutting down scheduler...")
        scheduler.shutdown()
        logger.info("✅ Scheduler stopped")

if __name__ == "__main__":
    main()
