"""
Scraper Registry - Plugin registration and discovery system.

Provides:
- @ScraperRegistry.register() decorator for auto-registration
- Discovery and loading of all scraper plugins
- Filtering by category, type, and status
"""

from typing import Optional, Type
import importlib
import logging
import pkgutil
from pathlib import Path

from .base import BaseScraper, ScraperType

logger = logging.getLogger(__name__)


class ScraperRegistry:
    """
    Central registry for all scraper plugins.

    Usage:
        @ScraperRegistry.register(category="big_tech")
        class MicrosoftScraper(HTTPScraper):
            config = ScraperConfig(company_slug="microsoft", ...)

        # Get a scraper
        scraper_cls = ScraperRegistry.get("microsoft")

        # Get all scrapers
        all_scrapers = ScraperRegistry.get_all()

        # Get by category
        big_tech = ScraperRegistry.get_by_category("big_tech")
    """

    _scrapers: dict[str, Type[BaseScraper]] = {}
    _categories: dict[str, list[str]] = {}  # category -> [slugs]
    _metadata: dict[str, dict] = {}  # slug -> {category, type, etc.}
    _loaded: bool = False

    @classmethod
    def register(cls, category: str = "other"):
        """
        Decorator to register a scraper class.

        Args:
            category: Category for grouping (big_tech, enterprise, finance, other)

        Returns:
            Decorator function
        """
        def decorator(scraper_cls: Type[BaseScraper]) -> Type[BaseScraper]:
            if not hasattr(scraper_cls, 'config'):
                raise ValueError(
                    f"Scraper {scraper_cls.__name__} must have a 'config' attribute"
                )

            slug = scraper_cls.config.company_slug

            if slug in cls._scrapers:
                logger.warning(f"Scraper '{slug}' already registered, overwriting")

            cls._scrapers[slug] = scraper_cls

            # Track category
            if category not in cls._categories:
                cls._categories[category] = []
            if slug not in cls._categories[category]:
                cls._categories[category].append(slug)

            # Store metadata
            cls._metadata[slug] = {
                "category": category,
                "company_name": scraper_cls.config.company_name,
                "scraper_type": scraper_cls.config.scraper_type.value,
                "careers_url": scraper_cls.config.careers_url,
                "rate_limit": scraper_cls.config.rate_limit,
            }

            logger.debug(
                f"Registered scraper: {slug} ({scraper_cls.__name__}) "
                f"in category '{category}'"
            )

            return scraper_cls

        return decorator

    @classmethod
    def get(cls, slug: str) -> Optional[Type[BaseScraper]]:
        """
        Get a scraper class by company slug.

        Args:
            slug: Company slug (e.g., "microsoft")

        Returns:
            Scraper class or None if not found
        """
        cls._ensure_loaded()
        return cls._scrapers.get(slug)

    @classmethod
    def get_all(cls) -> dict[str, Type[BaseScraper]]:
        """
        Get all registered scrapers.

        Returns:
            Dict of slug -> scraper class
        """
        cls._ensure_loaded()
        return cls._scrapers.copy()

    @classmethod
    def get_by_category(cls, category: str) -> dict[str, Type[BaseScraper]]:
        """
        Get scrapers by category.

        Args:
            category: Category name (big_tech, enterprise, finance, other)

        Returns:
            Dict of slug -> scraper class
        """
        cls._ensure_loaded()
        slugs = cls._categories.get(category, [])
        return {slug: cls._scrapers[slug] for slug in slugs if slug in cls._scrapers}

    @classmethod
    def get_by_type(cls, scraper_type: ScraperType) -> dict[str, Type[BaseScraper]]:
        """
        Get scrapers by type (HTTP or PLAYWRIGHT).

        Args:
            scraper_type: ScraperType.HTTP or ScraperType.PLAYWRIGHT

        Returns:
            Dict of slug -> scraper class
        """
        cls._ensure_loaded()
        return {
            slug: scraper_cls
            for slug, scraper_cls in cls._scrapers.items()
            if scraper_cls.config.scraper_type == scraper_type
        }

    @classmethod
    def get_metadata(cls, slug: str) -> Optional[dict]:
        """
        Get metadata for a scraper.

        Args:
            slug: Company slug

        Returns:
            Metadata dict or None
        """
        cls._ensure_loaded()
        return cls._metadata.get(slug)

    @classmethod
    def get_all_metadata(cls) -> dict[str, dict]:
        """
        Get metadata for all scrapers.

        Returns:
            Dict of slug -> metadata
        """
        cls._ensure_loaded()
        return cls._metadata.copy()

    @classmethod
    def list_categories(cls) -> list[str]:
        """
        List all categories.

        Returns:
            List of category names
        """
        cls._ensure_loaded()
        return list(cls._categories.keys())

    @classmethod
    def list_slugs(cls) -> list[str]:
        """
        List all registered company slugs.

        Returns:
            List of slugs
        """
        cls._ensure_loaded()
        return list(cls._scrapers.keys())

    @classmethod
    def count(cls) -> int:
        """
        Count total registered scrapers.

        Returns:
            Number of scrapers
        """
        cls._ensure_loaded()
        return len(cls._scrapers)

    @classmethod
    def _ensure_loaded(cls):
        """Ensure all scraper modules have been loaded."""
        if not cls._loaded:
            cls._load_all_scrapers()

    @classmethod
    def _load_all_scrapers(cls):
        """
        Discover and import all scraper modules.

        This walks through the scrapers package and imports all modules,
        which triggers the @register decorators.
        """
        if cls._loaded:
            return

        scrapers_path = Path(__file__).parent
        categories = ["big_tech", "enterprise", "finance", "other", "custom"]

        for category in categories:
            category_path = scrapers_path / category
            if not category_path.exists():
                continue

            # Import all Python files in the category directory
            for module_path in category_path.glob("*.py"):
                if module_path.name.startswith("_"):
                    continue

                module_name = f"scrapers.{category}.{module_path.stem}"
                try:
                    importlib.import_module(module_name)
                    logger.debug(f"Loaded scraper module: {module_name}")
                except Exception as e:
                    logger.error(f"Failed to load {module_name}: {e}")

        cls._loaded = True
        logger.info(
            f"Loaded {len(cls._scrapers)} scrapers in "
            f"{len(cls._categories)} categories"
        )

    @classmethod
    def reload(cls):
        """
        Reload all scrapers (useful for development).
        """
        cls._scrapers.clear()
        cls._categories.clear()
        cls._metadata.clear()
        cls._loaded = False
        cls._load_all_scrapers()


def get_scraper(
    slug: str,
    rate_limiter=None,
    browser_pool=None,
) -> Optional[BaseScraper]:
    """
    Factory function to instantiate a scraper.

    Args:
        slug: Company slug
        rate_limiter: Optional rate limiter
        browser_pool: Optional browser pool (for Playwright scrapers)

    Returns:
        Instantiated scraper or None
    """
    scraper_cls = ScraperRegistry.get(slug)
    if scraper_cls:
        return scraper_cls(rate_limiter=rate_limiter, browser_pool=browser_pool)
    return None


def list_all_scrapers() -> list[dict]:
    """
    List all scrapers with their metadata.

    Returns:
        List of scraper info dicts
    """
    return [
        {"slug": slug, **metadata}
        for slug, metadata in ScraperRegistry.get_all_metadata().items()
    ]
