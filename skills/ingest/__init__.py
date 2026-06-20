"""ingest — local-first web scraping + source ingestion into Qdrant.

    from skills.ingest import scrape, ingest, search
    scrape("https://example.com", structure=True)   # 0 cloud tokens
    ingest("https://example.com")                    # → Qdrant foundation
    search("topic")                                  # recall from the foundation
"""

from skills.ingest.ingest import (scrape, ingest, search, fetch, extract,
                                  resolve_embed, Scraped)

__all__ = ["scrape", "ingest", "search", "fetch", "extract",
           "resolve_embed", "Scraped"]
