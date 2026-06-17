from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import Settings
from app.models.enums import MetadataStatus


@dataclass(frozen=True)
class MetadataLookupResponse:
    success: bool
    lookup_source: str
    lookup_status: str
    doi: str | None = None
    title: str | None = None
    authors: list[str] | None = None
    year: int | None = None
    venue: str | None = None
    publisher: str | None = None
    abstract: str | None = None
    url: str | None = None
    raw_metadata_json: dict[str, Any] | None = None
    status_code: int | None = None
    error_code: str | None = None
    error_message: str | None = None


def _first_string(value: Any) -> str | None:
    if isinstance(value, list) and value:
        return _first_string(value[0])
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _extract_year(message: dict[str, Any]) -> int | None:
    for key in ("published-print", "published-online", "published", "issued", "created"):
        parts = message.get(key, {}).get("date-parts") if isinstance(message.get(key), dict) else None
        if isinstance(parts, list) and parts and isinstance(parts[0], list) and parts[0]:
            try:
                return int(parts[0][0])
            except (TypeError, ValueError):
                continue
    return None


def _extract_authors(message: dict[str, Any]) -> list[str]:
    authors: list[str] = []
    for author in message.get("author") or []:
        if not isinstance(author, dict):
            continue
        family = str(author.get("family") or "").strip()
        given = str(author.get("given") or "").strip()
        literal = str(author.get("name") or "").strip()
        if family and given:
            authors.append(f"{given} {family}")
        elif family:
            authors.append(family)
        elif literal:
            authors.append(literal)
    return authors


def _clean_abstract(value: Any) -> str | None:
    text = _first_string(value)
    if not text:
        return None
    # CrossRef sometimes returns very small JATS/HTML snippets.
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None

# Helper for title_similarity used in the title search fallback.
def _title_similarity(a: str, b: str) -> float:
    """Simple normalized title similarity using token overlap + sequence ratio."""
    import re as _re
    from difflib import SequenceMatcher

    def norm(text: str) -> str:
        text = text.lower()
        text = _re.sub(r"[^a-z0-9\s]", " ", text)
        return _re.sub(r"\s+", " ", text).strip()

    na, nb = norm(a), norm(b)
    if not na or not nb:
        return 0.0
    tokens_a, tokens_b = set(na.split()), set(nb.split())
    overlap = len(tokens_a & tokens_b) / len(tokens_a | tokens_b) if (tokens_a | tokens_b) else 0.0
    ratio = SequenceMatcher(None, na, nb).ratio()
    return max(overlap, ratio)


class CrossrefClient:
    """Small CrossRef DOI metadata client used by BE-5.

    The client only sends DOI values to CrossRef. It never sends uploaded document
    text, reference sections, or claim content.
    """

    def __init__(self, settings: Settings, *, http_client: httpx.Client | None = None) -> None:
        self.settings = settings
        self.base_url = settings.crossref_base_url.rstrip("/")
        self.timeout = settings.metadata_service_timeout_seconds
        self._client = http_client

    def lookup_by_doi(self, doi: str) -> MetadataLookupResponse:
        headers = {"User-Agent": self.settings.metadata_user_agent}
        params: dict[str, str] = {}
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto
        encoded_doi = doi.strip()
        url = f"{self.base_url}/works/{encoded_doi}"
        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                error_code="METADATA_LOOKUP_TIMEOUT",
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                error_code="METADATA_SERVICE_UNAVAILABLE",
                error_message=str(exc),
            )

        if response.status_code == 404:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                doi=doi,
                status_code=response.status_code,
                error_code="METADATA_UNAVAILABLE",
                error_message="CrossRef did not find metadata for this DOI.",
            )
        if response.status_code >= 400:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned HTTP {response.status_code}.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned malformed JSON: {exc}",
            )

        message = payload.get("message") if isinstance(payload, dict) else None
        if not isinstance(message, dict):
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                doi=doi,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message="CrossRef response did not contain a message object.",
                raw_metadata_json=payload if isinstance(payload, dict) else None,
            )

        return MetadataLookupResponse(
            success=True,
            lookup_source="CrossRef",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=str(message.get("DOI") or doi).lower(),
            title=_first_string(message.get("title")),
            authors=_extract_authors(message),
            year=_extract_year(message),
            venue=_first_string(message.get("container-title") or message.get("short-container-title")),
            publisher=_first_string(message.get("publisher")),
            abstract=_clean_abstract(message.get("abstract")),
            url=_first_string(message.get("URL")) or f"https://doi.org/{doi}",
            raw_metadata_json=payload,
            status_code=response.status_code,
        )
    
    # The title search is used as a fallback when no DOI could be extracted from the reference text.
    def search_by_title(
        self,
        title: str,
        *,
        authors: list[str] | None = None,
        year: int | None = None,
    ) -> "MetadataLookupResponse":
        """
        Search CrossRef by title (used as a fallback when no DOI was extracted
        from the reference text). Returns the best-matching work, or a
        METADATA_UNAVAILABLE response if no good match is found.

        Only the extracted title/authors/year are sent to CrossRef — never
        the raw reference text or any document content.
        """
        headers = {"User-Agent": self.settings.metadata_user_agent}
        params: dict[str, str] = {
            "query.bibliographic": title,
            "rows": "3",
        }
        if self.settings.crossref_mailto:
            params["mailto"] = self.settings.crossref_mailto

        url = f"{self.base_url}/works"

        try:
            if self._client is not None:
                response = self._client.get(url, headers=headers, params=params, timeout=self.timeout)
            else:
                with httpx.Client(timeout=self.timeout) as client:
                    response = client.get(url, headers=headers, params=params)
        except httpx.TimeoutException as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="METADATA_LOOKUP_TIMEOUT",
                error_message=str(exc),
            )
        except httpx.HTTPError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                error_code="METADATA_SERVICE_UNAVAILABLE",
                error_message=str(exc),
            )

        if response.status_code >= 400:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned HTTP {response.status_code}.",
            )

        try:
            payload = response.json()
        except ValueError as exc:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.LOOKUP_FAILED.value,
                status_code=response.status_code,
                error_code="DOI_LOOKUP_FAILED",
                error_message=f"CrossRef returned malformed JSON: {exc}",
            )

        items = (payload.get("message") or {}).get("items") if isinstance(payload, dict) else None
        if not items:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                status_code=response.status_code,
                error_code="METADATA_UNAVAILABLE",
                error_message="CrossRef title search returned no candidates.",
                raw_metadata_json=payload,
            )

        # Pick the best candidate by simple title similarity (+ optional year match)
        best = None
        best_score = -1.0
        for item in items:
            if not isinstance(item, dict):
                continue
            candidate_title = _first_string(item.get("title"))
            if not candidate_title:
                continue
            score = _title_similarity(title, candidate_title)
            candidate_year = _extract_year(item)
            if year is not None and candidate_year is not None and candidate_year == year:
                score += 0.1  # small boost for matching year
            if score > best_score:
                best_score = score
                best = item

        # Require a reasonably confident match before accepting the result —
        # otherwise we'd attach the wrong DOI to this reference.
        MIN_TITLE_SIMILARITY = 0.6
        if best is None or best_score < MIN_TITLE_SIMILARITY:
            return MetadataLookupResponse(
                success=False,
                lookup_source="CrossRef:title_search",
                lookup_status=MetadataStatus.METADATA_UNAVAILABLE.value,
                status_code=response.status_code,
                error_code="METADATA_UNAVAILABLE",
                error_message="CrossRef title search found no sufficiently similar match.",
                raw_metadata_json=payload,
            )

        message = best
        return MetadataLookupResponse(
            success=True,
            lookup_source="CrossRef:title_search",
            lookup_status=MetadataStatus.LOOKUP_SUCCEEDED.value,
            doi=str(message.get("DOI") or "").lower() or None,
            title=_first_string(message.get("title")),
            authors=_extract_authors(message),
            year=_extract_year(message),
            venue=_first_string(message.get("container-title") or message.get("short-container-title")),
            publisher=_first_string(message.get("publisher")),
            abstract=_clean_abstract(message.get("abstract")),
            url=_first_string(message.get("URL")),
            raw_metadata_json=payload,
            status_code=response.status_code,
        )





class DoiResolverClient:
    """Minimal DOI resolver URL helper.

    BE-5 uses this only as a safe URL fallback. It does not scrape publisher pages.
    """

    def __init__(self, settings: Settings) -> None:
        self.base_url = settings.doi_resolver_base_url.rstrip("/")

    def resolver_url(self, doi: str) -> str:
        return f"{self.base_url}/{doi}"
