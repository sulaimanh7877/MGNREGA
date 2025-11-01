# In-memory caching utilities

from functools import lru_cache
from datetime import datetime, timedelta
from typing import Any, Dict, Optional
import json
import logging

logger = logging.getLogger(__name__)

class CacheManager:
    """Simple TTL-based in-memory cache."""
    
    def __init__(self, max_entries: int = 10000, ttl_seconds: int = 300):
        self.cache: Dict[str, Dict[str, Any]] = {}
        self.max_entries = max_entries
        self.ttl_seconds = ttl_seconds
        self.hits = 0
        self.misses = 0
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if not expired."""
        if key not in self.cache:
            self.misses += 1
            return None
        
        entry = self.cache[key]
        if datetime.utcnow() > entry["expires_at"]:
            del self.cache[key]
            self.misses += 1
            return None
        
        self.hits += 1
        return entry["value"]
    
    def set(self, key: str, value: Any, ttl_seconds: Optional[int] = None) -> None:
        """Set value in cache with TTL."""
        if len(self.cache) >= self.max_entries:
            # Simple eviction: remove oldest entry
            oldest_key = min(self.cache.keys(), 
                           key=lambda k: self.cache[k]["created_at"])
            del self.cache[oldest_key]
            logger.debug(f"Evicted cache entry: {oldest_key}")
        
        ttl = ttl_seconds or self.ttl_seconds
        self.cache[key] = {
            "value": value,
            "created_at": datetime.utcnow(),
            "expires_at": datetime.utcnow() + timedelta(seconds=ttl)
        }
    
    def clear(self) -> None:
        """Clear entire cache."""
        self.cache.clear()
        logger.info("Cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get cache statistics."""
        total = self.hits + self.misses
        hit_rate = (self.hits / total * 100) if total > 0 else 0
        
        return {
            "total_entries": len(self.cache),
            "max_entries": self.max_entries,
            "hits": self.hits,
            "misses": self.misses,
            "hit_rate": f"{hit_rate:.2f}%",
            "ttl_seconds": self.ttl_seconds
        }

# Global cache instance
_cache = None

def init_cache(max_entries: int = 10000, ttl_seconds: int = 300) -> CacheManager:
    """Initialize global cache."""
    global _cache
    _cache = CacheManager(max_entries=max_entries, ttl_seconds=ttl_seconds)
    logger.info(f"Cache initialized: max_entries={max_entries}, ttl={ttl_seconds}s")
    return _cache

def get_cache() -> CacheManager:
    """Get global cache instance."""
    global _cache
    if _cache is None:
        _cache = CacheManager()
    return _cache

def cache_key(*args, **kwargs) -> str:
    """Generate cache key from arguments."""
    key_parts = [str(arg) for arg in args] + [f"{k}={v}" for k, v in kwargs.items()]
    return "|".join(key_parts)

def invalidate_cache_pattern(pattern: str) -> int:
    """Invalidate all cache entries matching pattern."""
    cache = get_cache()
    keys_to_delete = [k for k in cache.cache.keys() if pattern in k]
    for key in keys_to_delete:
        del cache.cache[key]
    logger.info(f"Invalidated {len(keys_to_delete)} cache entries matching '{pattern}'")
    return len(keys_to_delete)
