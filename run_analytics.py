#!/usr/bin/env python3
"""
Script to run analytics precomputation.

Usage:
    python run_analytics.py              # Precompute all analytics
    python run_analytics.py --full       # Full recompute
    python run_analytics.py --vacuum     # Optimize database after
"""

import argparse
import logging
import sys
from datetime import datetime
from analytics import precompute_all_analytics, get_analytics_metadata
from database import vacuum_db, get_record_count

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run MGNREGA Analytics Precomputation")
    parser.add_argument("--full", action="store_true", help="Full recompute (clear and rebuild)")
    parser.add_argument("--vacuum", action="store_true", help="Optimize database after computation")
    
    args = parser.parse_args()
    
    logger.info("=" * 60)
    logger.info("MGNREGA Analytics Precomputation")
    logger.info("=" * 60)
    
    start_time = datetime.utcnow()
    
    try:
        # Get record count
        total_records = get_record_count()
        logger.info(f"📊 Total records in database: {total_records}")
        
        if total_records == 0:
            logger.warning("⚠️ No data found in database. Please fetch data first using data_fetcher.py")
            sys.exit(1)
        
        # Run precomputation
        logger.info("🔄 Starting precomputation...")
        result = precompute_all_analytics()
        
        # Get metadata
        metadata = get_analytics_metadata()
        logger.info(f"✅ Precomputation complete!")
        logger.info(f"   - Metrics computed: {result['metrics_computed']}")
        logger.info(f"   - Duration: {result['duration_seconds']:.2f}s")
        logger.info(f"   - Total analytics metrics: {metadata['total_metrics']}")
        logger.info(f"   - Unique metric names: {metadata['unique_metric_names']}")
        logger.info(f"   - Unique districts: {metadata['unique_districts']}")
        logger.info(f"   - Last computed: {metadata['last_computed']}")
        
        # Optimize database if requested
        if args.vacuum:
            logger.info("🔧 Optimizing database...")
            vacuum_db()
            logger.info("✅ Database optimized")
        
        elapsed = (datetime.utcnow() - start_time).total_seconds()
        logger.info(f"Total time: {elapsed:.2f}s")
        logger.info("=" * 60)
        logger.info("✅ All done!")
        
    except Exception as e:
        logger.error(f"❌ Error: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
