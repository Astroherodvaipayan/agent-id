"""Read-only bridge to the existing Wyld Samaj creator search service."""

import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen


def configured():
    provider=os.getenv('WYLD_PROVIDER','local')
    return bool(os.getenv('WYLD_API_KEY')) if provider=='public' else bool(os.getenv('WYLD_SEARCH_URL')) if provider=='local' else False


def search(query: str, page=1, page_size=25, filters=None) -> dict:
    provider=os.getenv('WYLD_PROVIDER','local')
    if provider=='public':
        from .wyld_public import search as public_search
        return public_search(query,page,page_size,filters)
    if provider=='offline':raise RuntimeError('Creator search is offline; no provider call made')
    if provider!='local':raise ValueError('Unsupported creator provider')
    query = query.strip()
    if not query or len(query) > 200:
        raise ValueError("Search query must be 1–200 characters")
    base = os.getenv("WYLD_SEARCH_URL", "").rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "localhost") or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        raise ValueError("Configure WYLD_SEARCH_URL as the local Wyld backend origin")
    payload = json.dumps({"query": query, "page": 1, "page_size": 10, "filters": {}}).encode()
    headers = {"Content-Type": "application/json"}
    secret = os.getenv("WYLD_BACKEND_SECRET", "")
    if secret:
        headers["x-wyld-backend-secret"] = secret
    request = Request(base + "/search/v2", data=payload, headers=headers, method="POST")
    try:
        with urlopen(request, timeout=12) as response:
            data = json.load(response)
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError("Wyld creator search is unavailable; check its local backend and access configuration") from exc
    if not isinstance(data, dict) or not isinstance(data.get("items"), list):
        raise RuntimeError("Wyld creator search returned an invalid response")
    fields = ("username", "full_name", "followers_count", "engagement_rate", "fit_score", "match_reasons", "creator_location", "content_quality_summary")
    return {"source": "Wyld Samaj creator database /search/v2", "total": data.get("total", 0), "items": [{field: item.get(field) for field in fields} for item in data["items"][:10] if isinstance(item, dict)]}
