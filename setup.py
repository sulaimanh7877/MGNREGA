#!/usr/bin/env python3
"""
Quick setup script to initialize database and fetch initial data.

Usage:
    python setup.py
"""

import logging
import sys
from datetime import datetime
from database import init_db, get_record_count
from data_fetcher import fetch_and_upsert_all
from analytics import precompute_all_analytics

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    logger.info("=" * 60)
    logger.info("MGNREGA Analytics Platform - Setup")
    logger.info("=" * 60)
    
    try:
        # Step 1: Initialize database
        logger.info("\n📝 Step 1: Initializing database...")
        init_db()
        logger.info("✅ Database initialized")
        
        # Step 2: Fetch data from API
        logger.info("\n🌐 Step 2: Fetching data from data.gov.in API...")
        logger.info("   (This may take a few minutes...)")
        
        fetch_result = fetch_and_upsert_all(force_full_sync=True)
        
        if fetch_result.get("status") == "error":
            logger.error(f"❌ Data fetch failed: {fetch_result.get('error')}")
            logger.info("⚠️ Make sure your API_KEY is set correctly in config.py")
            sys.exit(1)
        
        logger.info(f"✅ Data fetched successfully!")
        logger.info(f"   - Total records: {fetch_result.get('total_processed')}")
        logger.info(f"   - Inserted: {fetch_result.get('inserted')}")
        logger.info(f"   - Updated: {fetch_result.get('updated')}")
        
        # Step 3: Precompute analytics
        logger.info("\n⚡ Step 3: Precomputing analytics...")
        logger.info("   (This may take a minute or two...)")
        
        analytics_result = precompute_all_analytics()
        
        logger.info(f"✅ Analytics precomputed!")
        logger.info(f"   - Metrics computed: {analytics_result.get('metrics_computed')}")
        logger.info(f"   - Duration: {analytics_result.get('duration_seconds'):.2f}s")
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("✅ Setup Complete!")
        logger.info("=" * 60)
        logger.info("\n📌 Next steps:")
        logger.info("   1. Start the API server: python run_server.py")
        logger.info("   2. Visit the API docs: http://localhost:8000/docs")
        logger.info("   3. Try some queries!")
        logger.info("\n📊 Data Summary:")
        logger.info(f"   - Total records: {get_record_count()}")
        logger.info("\n💡 Tips:")
        logger.info("   - Fetch new data: python data_fetcher.py")
        logger.info("   - Refresh analytics: python run_analytics.py")
        logger.info("   - Check logs: tail -f mgnrega_analytics.log")
        
    except Exception as e:
        logger.error(f"❌ Setup failed: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
