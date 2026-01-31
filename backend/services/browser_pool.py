"""
Playwright Browser Pool.

Manages a pool of browser instances for efficient scraping of
JavaScript-heavy websites. Provides context isolation and automatic cleanup.

Usage:
    pool = BrowserPool(size=2, max_pages=3)
    await pool.start()

    # Acquire a page
    page = await pool.acquire()
    try:
        await page.goto("https://example.com")
        # ... scrape ...
    finally:
        await pool.release(page)

    await pool.stop()
"""

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import Optional

from playwright.async_api import async_playwright, Browser, BrowserContext, Page

from config import settings

logger = logging.getLogger(__name__)


class BrowserPool:
    """
    Pool of Playwright browser instances.

    Features:
    - Configurable pool size
    - Context isolation for each scraping session
    - Page reuse within contexts
    - Automatic cleanup
    - Timeout protection
    """

    def __init__(
        self,
        size: int = None,
        max_pages_per_context: int = None,
        headless: bool = None,
    ):
        """
        Initialize the browser pool.

        Args:
            size: Number of browser contexts (default: BROWSER_POOL_SIZE)
            max_pages_per_context: Max pages per context (default: BROWSER_MAX_PAGES)
            headless: Run in headless mode (default: BROWSER_HEADLESS)
        """
        self.size = size or settings.browser_pool_size
        self.max_pages = max_pages_per_context or settings.browser_max_pages_per_context
        self.headless = headless if headless is not None else settings.browser_headless

        self._playwright = None
        self._browser: Optional[Browser] = None
        self._contexts: list[BrowserContext] = []
        self._available_pages: asyncio.Queue = asyncio.Queue()
        self._active_pages: set[Page] = set()
        self._started = False
        self._lock = asyncio.Lock()

    async def start(self):
        """Start the browser pool."""
        async with self._lock:
            if self._started:
                return

            logger.info(
                f"Starting browser pool: {self.size} contexts, "
                f"{self.max_pages} pages each, headless={self.headless}"
            )

            self._playwright = await async_playwright().start()
            self._browser = await self._playwright.chromium.launch(
                headless=self.headless,
                args=[
                    "--disable-dev-shm-usage",
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-gpu",
                ],
            )

            # Create contexts and pages
            for i in range(self.size):
                context = await self._browser.new_context(
                    viewport={"width": 1920, "height": 1080},
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    locale="en-US",
                    timezone_id="America/Los_Angeles",
                )
                self._contexts.append(context)

                for j in range(self.max_pages):
                    page = await context.new_page()
                    await self._available_pages.put(page)

            self._started = True
            total_pages = self.size * self.max_pages
            logger.info(f"Browser pool started with {total_pages} pages")

    async def stop(self):
        """Stop the browser pool and cleanup resources."""
        async with self._lock:
            if not self._started:
                return

            logger.info("Stopping browser pool...")

            # Close all contexts (this closes pages too)
            for context in self._contexts:
                try:
                    await context.close()
                except Exception as e:
                    logger.warning(f"Error closing context: {e}")

            # Close browser
            if self._browser:
                try:
                    await self._browser.close()
                except Exception as e:
                    logger.warning(f"Error closing browser: {e}")

            # Stop playwright
            if self._playwright:
                try:
                    await self._playwright.stop()
                except Exception as e:
                    logger.warning(f"Error stopping playwright: {e}")

            self._contexts.clear()
            self._active_pages.clear()
            self._available_pages = asyncio.Queue()
            self._started = False

            logger.info("Browser pool stopped")

    async def acquire(self, timeout: float = 30.0) -> Page:
        """
        Acquire a page from the pool.

        Args:
            timeout: Maximum time to wait for a page

        Returns:
            Playwright Page object

        Raises:
            asyncio.TimeoutError: If no page available within timeout
        """
        if not self._started:
            await self.start()

        try:
            page = await asyncio.wait_for(
                self._available_pages.get(),
                timeout=timeout,
            )
            self._active_pages.add(page)
            logger.debug(
                f"Acquired page, {self._available_pages.qsize()} remaining"
            )
            return page
        except asyncio.TimeoutError:
            logger.error("Timeout waiting for available page")
            raise

    async def release(self, page: Page):
        """
        Release a page back to the pool.

        The page is cleaned up (navigated to blank, cookies cleared)
        before being returned to the pool.

        Args:
            page: Page to release
        """
        if page not in self._active_pages:
            logger.warning("Attempting to release unknown page")
            return

        self._active_pages.discard(page)

        try:
            # Clean up the page
            await page.goto("about:blank")
            await page.context.clear_cookies()
        except Exception as e:
            logger.warning(f"Error cleaning up page: {e}")
            # Page might be broken, create a new one
            try:
                context = page.context
                await page.close()
                page = await context.new_page()
            except Exception as e2:
                logger.error(f"Error recreating page: {e2}")
                return

        await self._available_pages.put(page)
        logger.debug(
            f"Released page, {self._available_pages.qsize()} available"
        )

    @asynccontextmanager
    async def page(self, timeout: float = 30.0):
        """
        Context manager for acquiring and releasing a page.

        Usage:
            async with pool.page() as page:
                await page.goto(url)
                # ... use page ...
            # Page automatically released
        """
        page = await self.acquire(timeout)
        try:
            yield page
        finally:
            await self.release(page)

    @property
    def available_count(self) -> int:
        """Number of available pages."""
        return self._available_pages.qsize()

    @property
    def active_count(self) -> int:
        """Number of pages currently in use."""
        return len(self._active_pages)

    @property
    def total_count(self) -> int:
        """Total number of pages in the pool."""
        return self.size * self.max_pages

    def stats(self) -> dict:
        """Get pool statistics."""
        return {
            "started": self._started,
            "total_pages": self.total_count,
            "available_pages": self.available_count,
            "active_pages": self.active_count,
            "contexts": len(self._contexts),
            "headless": self.headless,
        }


# Global browser pool instance
_global_pool: Optional[BrowserPool] = None


async def get_browser_pool() -> BrowserPool:
    """
    Get the global browser pool instance.

    Creates and starts the pool if it doesn't exist.

    Returns:
        Global BrowserPool instance
    """
    global _global_pool
    if _global_pool is None:
        _global_pool = BrowserPool()
        await _global_pool.start()
    return _global_pool


async def shutdown_browser_pool():
    """Shutdown the global browser pool."""
    global _global_pool
    if _global_pool:
        await _global_pool.stop()
        _global_pool = None
