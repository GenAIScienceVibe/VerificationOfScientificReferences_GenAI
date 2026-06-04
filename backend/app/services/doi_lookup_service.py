"""
BE-4 DOI Metadata Lookup Service
----------------------------------
Fetches metadata from Crossref for references with known DOIs.
Falls back to title-based search for references without DOIs.

External APIs used (no API key required):
  - Crossref: https://api.crossref.org
  - OpenAlex: https://api.openalex.org (fallback)
"""
from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional
from urllib.parse import quote
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json

from sqlalchemy.orm import Session

from app.db.models import (
    Document,
    DocumentProcessingStatus,
    DoiStatus,
    MetadataStatus,
    Reference,
    SourceMetadata,
)
from app.db.repositories import (
    DocumentRepository,
    ReferenceRepository,
    SourceMetadataRepository,
)
from app.logger import logger


# ---------------------------------------------------------------------------
# HTTP helper (no external deps — uses stdlib urllib)
# ---------------------------------------------------------------------------

HEADERS = {
    "User-Agent": "refcheck-backend/1.0 (mailto:refcheck@example.com)",
    "Accept": "application/json",
}
TIMEOUT = 10  # seconds


def _get_json(url: str) -> Optional[Dict]:
    """Fetch JSON from URL using stdlib urllib."""
    try:
        req = Request(url, headers=HEADERS)
        with urlopen(req, timeout=TIMEOUT) as resp:
            if resp.status == 200:
                return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        if e.code == 404:
            return None
        logger.warning(f"[doi_lookup] HTTP {e.code} for {url}")
    except URLError as e:
        logger.warning(f"[doi_lookup] URL error for {url}: {e.reason}")
    except Exception as e:
        logger.warning(f"[doi_lookup] Error fetching {url}: {e}")
    return None


# ---------------------------------------------------------------------------
# Crossref lookup
# ---------------------------------------------------------------------------

def lookup_doi_crossref(doi: str) -> Optional[Dict]:
    """
    Fetch metadata from Crossref by DOI.
    Returns parsed metadata dict or None if not found.
    """
    url = f"https://api.crossref.org/works/{quote(doi, safe='')}"
    data = _get_json(url)
    if not data or data.get("status") != "ok":
        return None

    work = data.get("message", {})
    return _parse_crossref_work(work)


def _parse_crossref_work(work: Dict) -> Dict:
    """Parse a Crossref work object into our metadata format."""
    # Title
    title = None
    titles = work.get("title", [])
    if titles:
        title = titles[0]

    # Authors
    authors = []
    for author in work.get("author", []):
        given = author.get("given", "")
        family = author.get("family", "")
        if family:
            name = f"{family}, {given}".strip(", ")
            authors.append(name)

    # Year
    year = None
    for date_field in ["published-print", "published-online", "issued"]:
        date = work.get(date_field, {})
        parts = date.get("date-parts", [[]])
        if parts and parts[0]:
            year = parts[0][0]
            break

    # Journal/container
    journal = None
    containers = work.get("container-title", [])
    if containers:
        journal = containers[0]

    # Publisher
    publisher = work.get("publisher")

    # URL
    url = work.get("URL") or work.get("resource", {}).get("primary", {}).get("URL")

    # Abstract
    abstract = work.get("abstract")
    if abstract:
        # Strip JATS XML tags
        import re
        abstract = re.sub(r'<[^>]+>', '', abstract).strip()

    # DOI
    doi = work.get("DOI", "").lower()

    return {
        "doi": doi,
        "title": title,
        "authors": authors if authors else None,
        "year": year,
        "journal": journal,
        "publisher": publisher,
        "url": url,
        "abstract": abstract,
        "source": "crossref",
    }


# ---------------------------------------------------------------------------
# Title-based search (for MISSING DOI)
# ---------------------------------------------------------------------------

def search_by_title_crossref(title: str, authors: Optional[List[str]] = None,
                              year: Optional[int] = None) -> Optional[Dict]:
    """
    Search Crossref by title (and optionally authors/year).
    Returns best match or None.
    """
    query = title
    if authors:
        # Add first author surname
        first_author = authors[0].split(",")[0].strip()
        query = f"{title} {first_author}"

    url = (
        f"https://api.crossref.org/works"
        f"?query={quote(query)}"
        f"&rows=3"
        f"&select=DOI,title,author,published-print,published-online,issued,"
        f"container-title,publisher,URL,abstract"
    )
    if year:
        url += f"&filter=from-pub-date:{year},until-pub-date:{year}"

    data = _get_json(url)
    if not data or data.get("status") != "ok":
        return None

    items = data.get("message", {}).get("items", [])
    if not items:
        return None

    # Return best match (first result)
    result = _parse_crossref_work(items[0])
    result["found_via"] = "title_search"
    return result


# ---------------------------------------------------------------------------
# Match scoring
# ---------------------------------------------------------------------------

def compute_match_score(ref: Reference, metadata: Dict) -> float:
    """
    Compute a quality score (0.0–1.0) comparing extracted reference
    with fetched metadata.

    Checks: title match, year match, author match.
    """
    score = 0.0
    checks = 0

    # Title match
    if ref.extracted_title and metadata.get("title"):
        ref_title = ref.extracted_title.lower().strip()
        meta_title = metadata["title"].lower().strip()
        # Substring match (handles truncated titles)
        if ref_title in meta_title or meta_title in ref_title:
            score += 1.0
        else:
            # Word overlap
            ref_words = set(ref_title.split())
            meta_words = set(meta_title.split())
            overlap = len(ref_words & meta_words)
            if ref_words:
                score += overlap / len(ref_words)
        checks += 1

    # Year match
    if ref.extracted_year and metadata.get("year"):
        if ref.extracted_year == metadata["year"]:
            score += 1.0
        checks += 1

    # Author match (first author surname)
    if ref.extracted_authors and metadata.get("authors"):
        ref_first = ref.extracted_authors[0].split(",")[0].lower().strip()
        meta_authors_lower = [a.split(",")[0].lower().strip()
                               for a in metadata["authors"]]
        if ref_first in meta_authors_lower:
            score += 1.0
        checks += 1

    if checks == 0:
        return 0.5  # No data to compare — neutral score

    return round(score / checks, 2)


# ---------------------------------------------------------------------------
# Store metadata
# ---------------------------------------------------------------------------

def _store_metadata(
    reference_id: str,
    metadata: Dict,
    match_score: float,
    db: Session,
) -> SourceMetadata:
    """Create or update SourceMetadata for a reference."""
    meta_repo = SourceMetadataRepository(db)
    existing = meta_repo.get_by_reference(reference_id)

    if existing:
        db.delete(existing)
        db.flush()

    meta = SourceMetadata(
        reference_id=reference_id,
        metadata_status=MetadataStatus.LOOKUP_SUCCEEDED,
        doi=metadata.get("doi"),
        title=metadata.get("title"),
        authors=metadata.get("authors"),
        year=metadata.get("year"),
        journal=metadata.get("journal"),
        publisher=metadata.get("publisher"),
        url=metadata.get("url"),
        abstract=metadata.get("abstract"),
        fetched_at=__import__("datetime").datetime.now(
            __import__("datetime").timezone.utc
        ),
    )
    db.add(meta)
    db.flush()
    return meta


# ---------------------------------------------------------------------------
# Single reference lookup
# ---------------------------------------------------------------------------

@dataclass
class LookupResult:
    reference_id: str
    doi_status: DoiStatus
    metadata_status: MetadataStatus
    match_score: Optional[float] = None
    title_match: bool = False
    year_match: bool = False
    author_match: bool = False
    cached: bool = False
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.metadata_status == MetadataStatus.LOOKUP_SUCCEEDED


def lookup_single_reference(
    reference_id: str,
    db: Session,
    force: bool = False,
) -> LookupResult:
    """
    Perform DOI metadata lookup for a single reference.
    Tries DOI lookup first, then title search for MISSING DOIs.
    """
    ref_repo = ReferenceRepository(db)
    ref = ref_repo.get(reference_id)
    if not ref:
        return LookupResult(
            reference_id=reference_id,
            doi_status=DoiStatus.MISSING,
            metadata_status=MetadataStatus.UNAVAILABLE,
            error=f"Reference '{reference_id}' not found.",
        )

    # Check if already looked up
    meta_repo = SourceMetadataRepository(db)
    existing = meta_repo.get_by_reference(reference_id)
    if existing and existing.metadata_status == MetadataStatus.LOOKUP_SUCCEEDED and not force:
        logger.info(f"[doi_lookup] {reference_id} — using cached metadata")
        match_score = ref.metadata_match_score or 0.0
        return LookupResult(
            reference_id=reference_id,
            doi_status=ref.doi_status,
            metadata_status=MetadataStatus.LOOKUP_SUCCEEDED,
            match_score=match_score,
            title_match=match_score >= 0.8,
            year_match=match_score >= 0.5,
            author_match=match_score >= 0.6,
            cached=True,
        )

    metadata = None

    # Strategy 1: DOI lookup
    if ref.doi_status == DoiStatus.FOUND and ref.doi_normalized:
        logger.info(f"[doi_lookup] {reference_id} — looking up DOI: {ref.doi_normalized}")
        metadata = lookup_doi_crossref(ref.doi_normalized)
        if metadata:
            logger.info(f"[doi_lookup] {reference_id} — DOI found in Crossref")

    # Strategy 2: Title search for MISSING DOI
    if not metadata and ref.doi_status == DoiStatus.MISSING:
        title = ref.extracted_title
        if title and len(title) > 10:
            logger.info(f"[doi_lookup] {reference_id} — title search: {title[:50]}")
            metadata = search_by_title_crossref(
                title=title,
                authors=ref.extracted_authors,
                year=ref.extracted_year,
            )
            if metadata:
                logger.info(f"[doi_lookup] {reference_id} — found via title search, DOI: {metadata.get('doi')}")
                # Update reference DOI if found
                if metadata.get("doi"):
                    ref.extracted_doi = metadata["doi"]
                    ref.doi_normalized = metadata["doi"]
                    ref.doi_status = DoiStatus.FOUND

    if not metadata:
        ref.metadata_status = MetadataStatus.LOOKUP_FAILED
        db.commit()
        logger.info(f"[doi_lookup] {reference_id} — lookup failed")
        return LookupResult(
            reference_id=reference_id,
            doi_status=ref.doi_status,
            metadata_status=MetadataStatus.LOOKUP_FAILED,
        )

    # Compute match score
    match_score = compute_match_score(ref, metadata)

    # Store metadata
    _store_metadata(reference_id, metadata, match_score, db)

    # Update reference
    ref.metadata_status = MetadataStatus.LOOKUP_SUCCEEDED
    ref.metadata_match_score = match_score
    if metadata.get("doi") and not ref.doi_normalized:
        ref.doi_normalized = metadata["doi"]
        ref.doi_status = DoiStatus.FOUND

    db.commit()

    title_match = False
    year_match = False
    author_match = False

    if ref.extracted_title and metadata.get("title"):
        title_match = ref.extracted_title.lower() in metadata["title"].lower() or \
                      metadata["title"].lower() in ref.extracted_title.lower()
    if ref.extracted_year and metadata.get("year"):
        year_match = ref.extracted_year == metadata["year"]
    if ref.extracted_authors and metadata.get("authors"):
        ref_first = ref.extracted_authors[0].split(",")[0].lower()
        year_match = year_match
        author_match = any(
            ref_first in a.split(",")[0].lower()
            for a in metadata["authors"]
        )

    return LookupResult(
        reference_id=reference_id,
        doi_status=ref.doi_status,
        metadata_status=MetadataStatus.LOOKUP_SUCCEEDED,
        match_score=match_score,
        title_match=title_match,
        year_match=year_match,
        author_match=author_match,
        cached=False,
    )


# ---------------------------------------------------------------------------
# Bulk lookup for document
# ---------------------------------------------------------------------------

@dataclass
class BulkLookupResult:
    document_id: str
    total: int = 0
    succeeded: int = 0
    failed: int = 0
    cached: int = 0
    results: List[LookupResult] = field(default_factory=list)
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None


def lookup_all_references(
    document_id: str,
    db: Session,
    force: bool = False,
) -> BulkLookupResult:
    """
    Perform DOI metadata lookup for all references in a document.
    Includes a small delay between requests to be polite to Crossref.
    """
    doc_repo = DocumentRepository(db)
    ref_repo = ReferenceRepository(db)

    doc = doc_repo.get(document_id)
    if not doc:
        return BulkLookupResult(
            document_id=document_id,
            error=f"Document '{document_id}' not found.",
        )

    doc.status = DocumentProcessingStatus.DOI_VERIFYING
    db.commit()
    logger.info(f"[doi_lookup] {document_id} — starting bulk DOI lookup")

    refs = ref_repo.list_by_document(document_id)
    result = BulkLookupResult(document_id=document_id, total=len(refs))

    for i, ref in enumerate(refs):
        try:
            lookup = lookup_single_reference(ref.reference_id, db, force=force)
            result.results.append(lookup)

            if lookup.cached:
                result.cached += 1
            elif lookup.success:
                result.succeeded += 1
            else:
                result.failed += 1

            # Polite delay — 1 request per second max
            if not lookup.cached and i < len(refs) - 1:
                time.sleep(1.0)

        except Exception as e:
            logger.error(f"[doi_lookup] Error looking up {ref.reference_id}: {e}")
            result.failed += 1

    doc.status = DocumentProcessingStatus.DOI_VERIFIED
    db.commit()

    logger.info(
        f"[doi_lookup] {document_id} — DOI_VERIFIED: "
        f"{result.succeeded} succeeded, {result.failed} failed, "
        f"{result.cached} cached"
    )
    return result
