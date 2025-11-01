#!/usr/bin/env python3
"""
Script to run the FastAPI server.

Usage:
    python run_server.py
    # or with custom host/port:
    python run_server.py --host 127.0.0.1 --port 9000
"""

import argparse
import logging
import uvicorn
from config import DEBUG, FASTAPI_HOST, FASTAPI_PORT, FASTAPI_WORKERS

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    parser = argparse.ArgumentParser(description="Run MGNREGA Analytics API")
    parser.add_argument("--host", default=FASTAPI_HOST, help=f"Host to bind (default: {FASTAPI_HOST})")
    parser.add_argument("--port", type=int, default=FASTAPI_PORT, help=f"Port to bind (default: {FASTAPI_PORT})")
    parser.add_argument("--reload", action="store_true", default=DEBUG, help="Auto-reload on code changes")
    parser.add_argument("--workers", type=int, default=FASTAPI_WORKERS if not DEBUG else 1, 
                       help=f"Number of workers (default: {FASTAPI_WORKERS if not DEBUG else 1})")
    
    args = parser.parse_args()
    
    logger.info(f"🚀 Starting MGNREGA Analytics API")
    logger.info(f"   Host: {args.host}")
    logger.info(f"   Port: {args.port}")
    logger.info(f"   Workers: {args.workers}")
    logger.info(f"   Reload: {args.reload}")
    logger.info(f"   Visit: http://{args.host}:{args.port}/docs")
    
    uvicorn.run(
        "main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        workers=1 if args.reload else args.workers,
        log_level="info"
    )

if __name__ == "__main__":
    main()
