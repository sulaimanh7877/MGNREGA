# Database initialization and connection management

import sqlite3
from contextlib import closing
from datetime import datetime
import logging
from config import DB_PATH, DB_TIMEOUT, FIELDS, UNIQUE_KEYS, SQLITE_WAL_MODE, SQLITE_CACHE_SIZE, SQLITE_SYNCHRONOUS

logger = logging.getLogger(__name__)

def get_connection(db_path=DB_PATH, timeout=DB_TIMEOUT):
    """Get a SQLite connection with proper configuration."""
    conn = sqlite3.connect(db_path, timeout=timeout)
    conn.row_factory = sqlite3.Row
    
    # Performance tuning
    if SQLITE_WAL_MODE:
        conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(f"PRAGMA cache_size={SQLITE_CACHE_SIZE}")
    conn.execute(f"PRAGMA synchronous={SQLITE_SYNCHRONOUS}")
    conn.execute("PRAGMA foreign_keys=ON")
    
    return conn

def init_db(db_path=DB_PATH):
    """Initialize SQLite database with required tables."""
    conn = get_connection(db_path)
    try:
        # Create main data table
        columns = []
        for f in FIELDS:
            if f["type"] in ("text", "keyword"):
                columns.append(f"{f['id']} TEXT")
            elif f["type"] == "long":
                columns.append(f"{f['id']} INTEGER")
            else:
                columns.append(f"{f['id']} TEXT")
        
        unique_keys = ", ".join(UNIQUE_KEYS)
        create_mgnrega_query = f"""
        CREATE TABLE IF NOT EXISTS mgnrega (
            {", ".join(columns)},
            UNIQUE ({unique_keys})
        )
        """
        conn.execute(create_mgnrega_query)
        logger.info("✅ Created mgnrega table")
        
        # Create metadata table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS mgnrega_meta (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT UNIQUE,
                last_updated TEXT,
                total_records INTEGER,
                last_checked TEXT
            )
        """)
        logger.info("✅ Created mgnrega_meta table")
        
        # Create analytics metrics table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS analytics_metrics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                fin_year TEXT,
                month TEXT,
                state_code TEXT,
                district_code TEXT,
                metric_name TEXT,
                metric_value REAL,
                computed_at TEXT,
                UNIQUE(fin_year, month, state_code, district_code, metric_name)
            )
        """)
        logger.info("✅ Created analytics_metrics table")
        
        # Create indices for performance
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_year_month ON analytics_metrics(fin_year, month)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_analytics_district ON analytics_metrics(district_code)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mgnrega_year_month ON mgnrega(fin_year, month)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_mgnrega_district ON mgnrega(district_code)")
        logger.info("✅ Created database indices")
        
        conn.commit()
        logger.info("✅ Database initialized successfully")
        
    except Exception as e:
        logger.error(f"❌ Error initializing database: {e}")
        raise
    finally:
        conn.close()

def get_meta():
    """Get metadata about data freshness."""
    with closing(get_connection()) as conn:
        row = conn.execute("""
            SELECT last_updated, total_records FROM mgnrega_meta WHERE source='main'
        """).fetchone()
        return dict(row) if row else None

def update_meta(last_updated, total_records):
    """Update metadata tracking."""
    with closing(get_connection()) as conn:
        conn.execute("""
        INSERT INTO mgnrega_meta (source, last_updated, total_records, last_checked)
        VALUES ('main', ?, ?, ?)
        ON CONFLICT(source) DO UPDATE SET
            last_updated=excluded.last_updated,
            total_records=excluded.total_records,
            last_checked=excluded.last_checked
        """, (last_updated, total_records, datetime.utcnow().isoformat()))
        conn.commit()
        logger.info(f"✅ Updated metadata: {total_records} records, last_updated: {last_updated}")

def get_record_count():
    """Get total number of records in mgnrega table."""
    with closing(get_connection()) as conn:
        count = conn.execute("SELECT COUNT(*) FROM mgnrega").fetchone()[0]
        return count

def get_distinct_values(column_name):
    """Get distinct values for a column."""
    with closing(get_connection()) as conn:
        rows = conn.execute(f"SELECT DISTINCT {column_name} FROM mgnrega ORDER BY {column_name}").fetchall()
        return [row[0] for row in rows]

def vacuum_db():
    """Optimize database (vacuum and reindex)."""
    with closing(get_connection()) as conn:
        conn.execute("VACUUM")
        conn.execute("REINDEX")
        logger.info("✅ Database optimized")
