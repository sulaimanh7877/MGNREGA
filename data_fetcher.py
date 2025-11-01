# Data fetching from data.gov.in API with incremental updates

import requests
import logging
import time
from datetime import datetime
from contextlib import closing
from typing import Dict, List, Any
from database import get_connection, update_meta, get_meta
from config import (
    API_BASE_URL, API_KEY, API_TIMEOUT, TARGET_STATE, BATCH_SIZE,
    UNIQUE_KEYS, FIELDS, API_RETRY_ATTEMPTS, API_RETRY_DELAY
)

logger = logging.getLogger(__name__)

def to_number(val):
    """Safely convert value to float/int if possible, else return None."""
    try:
        if val is None:
            return None
        if isinstance(val, (int, float)):
            return val
        return float(str(val).replace(",", ""))
    except:
        return None

def upsert_record(con, new_data: Dict[str, Any]):
    """Upsert a single record into mgnrega table."""
    cursor = con.cursor()
    
    # Check if record exists
    select_query = f"""
    SELECT * FROM mgnrega
    WHERE {" AND ".join([f"{k}=?" for k in UNIQUE_KEYS])}
    """
    existing = cursor.execute(select_query, [new_data.get(k) for k in UNIQUE_KEYS]).fetchone()
    
    if existing:
        # Fetch column names for mapping
        col_names = [desc[0] for desc in cursor.description]
        existing_data = dict(zip(col_names, existing))
        
        updates = {}
        for field in FIELDS:
            fid = field["id"]
            if fid in UNIQUE_KEYS:
                continue
            
            old_val = existing_data.get(fid)
            new_val = new_data.get(fid)
            
            # Try numeric comparison safely
            old_num = to_number(old_val)
            new_num = to_number(new_val)
            
            if new_num is not None and old_num is not None:
                # numeric comparison - update if new is larger
                if new_num > old_num:
                    updates[fid] = new_val
            else:
                # string or text update if changed
                if str(new_val) != str(old_val):
                    updates[fid] = new_val
        
        if updates:
            set_clause = ", ".join([f"{k}=?" for k in updates.keys()])
            where_clause = " AND ".join([f"{k}=?" for k in UNIQUE_KEYS])
            update_query = f"UPDATE mgnrega SET {set_clause} WHERE {where_clause}"
            cursor.execute(update_query, list(updates.values()) + [new_data.get(k) for k in UNIQUE_KEYS])
            con.commit()
            logger.debug(f"✅ Updated: {new_data.get('district_name')} ({len(updates)} fields)")
            return "updated"
        else:
            logger.debug(f"ℹ️ No updates needed for {new_data.get('district_name')}")
            return "unchanged"
    else:
        # No record exists - insert new one
        cols = ", ".join(new_data.keys())
        placeholders = ", ".join(["?"] * len(new_data))
        insert_query = f"INSERT INTO mgnrega ({cols}) VALUES ({placeholders})"
        cursor.execute(insert_query, list(new_data.values()))
        con.commit()
        logger.debug(f"🆕 Inserted: {new_data.get('district_name')}")
        return "inserted"

def fetch_data_batch(offset: int, limit: int) -> tuple[List[Dict], int, bool]:
    """Fetch a batch of records from API."""
    for attempt in range(API_RETRY_ATTEMPTS):
        try:
            params = {
                "api-key": API_KEY,
                "format": "json",
                "offset": offset,
                "limit": limit,
                "filters[state_name]": TARGET_STATE
            }
            
            response = requests.get(API_BASE_URL, params=params, timeout=API_TIMEOUT)
            response.raise_for_status()
            
            data = response.json()
            total_records = data.get("total", 0)
            records = data.get("records", [])
            
            logger.info(f"✅ Fetched batch: offset={offset}, count={len(records)}, total={total_records}")
            return records, total_records, True
            
        except requests.exceptions.RequestException as e:
            if attempt < API_RETRY_ATTEMPTS - 1:
                logger.warning(f"⚠️ Attempt {attempt + 1} failed: {e}, retrying in {API_RETRY_DELAY}s...")
                time.sleep(API_RETRY_DELAY)
            else:
                logger.error(f"❌ Failed after {API_RETRY_ATTEMPTS} attempts: {e}")
                return [], 0, False
    
    return [], 0, False

def fetch_and_upsert_all(force_full_sync: bool = False):
    """Main data fetching and upserting function."""
    logger.info("🚀 Starting data fetch and upsert...")
    
    con = get_connection()
    try:
        # Get last fetch metadata
        meta = get_meta()
        last_updated = meta.get("last_updated") if meta else None
        
        if force_full_sync:
            logger.info("🔄 Force full sync requested")
            current_offset = 0
        else:
            current_offset = 0  # For incremental, decide based on last_updated
            logger.info(f"Last update: {last_updated}")
        
        total_records_from_api = 1
        batch_count = 0
        insert_count = 0
        update_count = 0
        unchanged_count = 0
        
        while current_offset < total_records_from_api:
            records, total_from_api, success = fetch_data_batch(current_offset, BATCH_SIZE)
            
            if not success:
                logger.error("Failed to fetch data, stopping")
                break
            
            if not records:
                break
            
            total_records_from_api = total_from_api
            
            for rec in records:
                result = upsert_record(con, rec)
                if result == "inserted":
                    insert_count += 1
                elif result == "updated":
                    update_count += 1
                else:
                    unchanged_count += 1
            
            batch_count += 1
            current_offset += len(records)
            logger.info(f"⏳ Progress: {current_offset}/{total_records_from_api} records processed")
            
            # Polite delay between requests
            time.sleep(2)
        
        # Update metadata
        update_meta(datetime.utcnow().isoformat(), current_offset)
        
        logger.info(f"""
        ✅ Data fetch complete:
        - Total processed: {current_offset}
        - Inserted: {insert_count}
        - Updated: {update_count}
        - Unchanged: {unchanged_count}
        - Batches: {batch_count}
        """)
        
        return {
            "status": "success",
            "total_processed": current_offset,
            "inserted": insert_count,
            "updated": update_count,
            "unchanged": unchanged_count
        }
        
    except Exception as e:
        logger.error(f"❌ Error during fetch/upsert: {e}", exc_info=True)
        return {"status": "error", "error": str(e)}
    
    finally:
        con.close()

if __name__ == "__main__":
    import logging
    logging.basicConfig(level=logging.INFO)
    result = fetch_and_upsert_all(force_full_sync=True)
    print(result)
