"""
Subscription verification service.

Verifies user subscription status via capra-backend API
to determine if user has access to the jobs portal.
"""

import httpx
import os
from typing import Dict, Any
from functools import lru_cache
import time

# Configuration
CAPRA_BACKEND_URL = os.getenv('CAPRA_BACKEND_URL', 'https://capra-backend.up.railway.app')
CAPRA_INTERNAL_API_KEY = os.getenv('CAPRA_INTERNAL_API_KEY', '')

# Cache TTL in seconds (5 minutes)
CACHE_TTL = 300
_subscription_cache: Dict[int, tuple] = {}  # user_id -> (result, timestamp)


async def verify_subscription(user_id: int) -> Dict[str, Any]:
    """
    Verify user has quarterly_pro subscription via capra backend.

    Args:
        user_id: The user's ID (consistent across Cariara OAuth)

    Returns:
        Dict with hasAccess, planType, status, currentPeriodEnd
    """
    # Check cache first
    cached = _subscription_cache.get(user_id)
    if cached:
        result, timestamp = cached
        if time.time() - timestamp < CACHE_TTL:
            return result

    # Verify we have the API key configured
    if not CAPRA_INTERNAL_API_KEY:
        # No API key configured - deny access by default
        return {
            "hasAccess": False,
            "planType": "unknown",
            "status": "error",
            "error": "Subscription verification not configured"
        }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{CAPRA_BACKEND_URL}/api/billing/verify-subscription/{user_id}",
                headers={"X-API-Key": CAPRA_INTERNAL_API_KEY},
                timeout=5.0
            )

            if response.status_code == 200:
                result = response.json()
                # Cache the result
                _subscription_cache[user_id] = (result, time.time())
                return result
            elif response.status_code == 401:
                return {
                    "hasAccess": False,
                    "planType": "unknown",
                    "status": "error",
                    "error": "Invalid API key"
                }
            else:
                return {
                    "hasAccess": False,
                    "planType": "unknown",
                    "status": "error",
                    "error": f"API returned {response.status_code}"
                }
    except httpx.TimeoutException:
        return {
            "hasAccess": False,
            "planType": "unknown",
            "status": "error",
            "error": "Subscription service timeout"
        }
    except Exception as e:
        return {
            "hasAccess": False,
            "planType": "unknown",
            "status": "error",
            "error": str(e)
        }


def clear_subscription_cache(user_id: int = None):
    """
    Clear subscription cache for a specific user or all users.
    """
    global _subscription_cache
    if user_id:
        _subscription_cache.pop(user_id, None)
    else:
        _subscription_cache = {}
