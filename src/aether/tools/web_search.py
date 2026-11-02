"""
Web Search Tool for Aether Agents.

Provides web search capabilities for workforce research agents:
- Textual query processing with configurable result limit
- Strict 10-second default timeout
- Zero mandatory API keys (uses DuckDuckGo / extensible backend)
- Structured results with Title, URL, and Snippet
- Graceful error handling (timeout, HTTP error, zero results)
"""
from __future__ import annotations

import html
import re
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

from aether.tools.base import Tool, ToolClassification
from aether.tools.decorator import tool


@dataclass(slots=True)
class WebSearchResult:
    """Structured search result contract."""
    title: str
    url: str
    snippet: str

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
        }


class BaseWebSearchBackend(ABC):
    """Abstract interface for pluggable search engines (DuckDuckGo, Bing, Tavily, Mock)."""

    @abstractmethod
    def search(self, query: str, max_results: int = 5, timeout: float = 10.0) -> list[WebSearchResult]:
        """Perform search query and return list of WebSearchResult objects."""
        raise NotImplementedError


class DuckDuckGoSearchBackend(BaseWebSearchBackend):
    """
    Zero-key Web search backend querying DuckDuckGo HTML with strict timeout and clean regex parsing.
    """

    ENDPOINT = "https://html.duckduckgo.com/html/"
    DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Aether/1.5"

    def __init__(self, timeout: float = 10.0, user_agent: str | None = None) -> None:
        self.timeout = min(timeout, 10.0)
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT

    def search(self, query: str, max_results: int = 5, timeout: float = 10.0) -> list[WebSearchResult]:
        effective_timeout = min(timeout, self.timeout)
        data = urllib.parse.urlencode({"q": query, "b": ""}).encode("utf-8")
        req = urllib.request.Request(
            self.ENDPOINT,
            data=data,
            headers={
                "User-Agent": self.user_agent,
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=effective_timeout) as resp:
                html_text = resp.read().decode("utf-8", errors="replace")
                return self._parse_html(html_text, max_results=max_results)
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError):
            # Graceful return on any network, timeout, or rate-limit failure
            return []

    def _parse_html(self, html_content: str, max_results: int = 5) -> list[WebSearchResult]:
        results: list[WebSearchResult] = []

        # Find result containers in DuckDuckGo HTML
        # Match pattern: <a class="result__url" href="..."> or <a class="result__snippet" ...>
        # Match <a class="result__snippet"[^>]*>(.*?)</a>
        # One chunk per result: from a result container to the next (a non-greedy "</div></div>" stopped before the snippet).
        result_blocks = re.split(r'<div[^>]*class="[^"]*\bresult\s+results_links[^"]*"[^>]*>', html_content)[1:]

        if not result_blocks:
            # Fallback block matching
            result_blocks = re.findall(
                r'<a[^>]*class="result__a"[^>]*href="(?P<url>[^"]+)"[^>]*>(?P<title>.*?)</a>.*?'
                r'<a[^>]*class="result__snippet"[^>]*>(?P<snippet>.*?)</a>',
                html_content,
                re.DOTALL,
            )
            for item in result_blocks[:max_results]:
                raw_url, raw_title, raw_snippet = item
                clean_url = self._clean_url(raw_url)
                clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
                clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()
                if clean_url and clean_title:
                    results.append(WebSearchResult(title=clean_title, url=clean_url, snippet=clean_snippet))
            return results

        for block in result_blocks[:max_results]:
            title_match = re.search(r'<a[^>]*class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', block, re.DOTALL)
            snippet_match = re.search(r'<a[^>]*class="result__snippet"[^>]*>(.*?)</a>', block, re.DOTALL)

            if title_match:
                raw_url = title_match.group(1)
                raw_title = title_match.group(2)
                raw_snippet = snippet_match.group(1) if snippet_match else ""

                clean_url = self._clean_url(raw_url)
                clean_title = html.unescape(re.sub(r"<[^>]+>", "", raw_title)).strip()
                clean_snippet = html.unescape(re.sub(r"<[^>]+>", "", raw_snippet)).strip()

                if clean_url and clean_title:
                    results.append(WebSearchResult(
                        title=clean_title,
                        url=clean_url,
                        snippet=clean_snippet,
                    ))

        return results

    def _clean_url(self, raw_url: str) -> str:
        # Resolve DuckDuckGo tracking redirects: /l/?uddg=https%3A%2F%2Fexample.com
        if "uddg=" in raw_url:
            match = re.search(r'uddg=([^&]+)', raw_url)
            if match:
                return urllib.parse.unquote(match.group(1))
        if raw_url.startswith("//"):
            return "https:" + raw_url
        return raw_url


def _get_json(req: urllib.request.Request, timeout: float) -> Any:
    import json

    with urllib.request.urlopen(req, timeout=min(timeout, 10.0)) as resp:  # noqa: S310 - fixed https endpoints
        return json.loads(resp.read().decode("utf-8", "replace"))


def _plain(text: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", text or "")).strip()


class BraveSearchBackend(BaseWebSearchBackend):
    """Brave Search API (the user's own key, free tier available): no CAPTCHA, works with any model."""

    ENDPOINT = "https://api.search.brave.com/res/v1/web/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5, timeout: float = 10.0) -> list[WebSearchResult]:
        url = f"{self.ENDPOINT}?{urllib.parse.urlencode({'q': query, 'count': max(1, min(max_results, 20))})}"
        req = urllib.request.Request(url, headers={"Accept": "application/json", "X-Subscription-Token": self.api_key})
        data = _get_json(req, timeout)
        rows = ((data or {}).get("web") or {}).get("results") or []
        return [WebSearchResult(title=_plain(r.get("title", "")), url=str(r.get("url", "")), snippet=_plain(r.get("description", "")))
                for r in rows if r.get("url")][:max_results]


class TavilySearchBackend(BaseWebSearchBackend):
    """Tavily search API (the user's own key, free tier available): results made for models to read."""

    ENDPOINT = "https://api.tavily.com/search"

    def __init__(self, api_key: str) -> None:
        self.api_key = api_key

    def search(self, query: str, max_results: int = 5, timeout: float = 10.0) -> list[WebSearchResult]:
        import json

        body = json.dumps({"query": query, "max_results": max(1, min(max_results, 10)), "search_depth": "basic"}).encode()
        req = urllib.request.Request(self.ENDPOINT, data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.api_key}"})
        data = _get_json(req, timeout)
        rows = (data or {}).get("results") or []
        return [WebSearchResult(title=_plain(r.get("title", "")), url=str(r.get("url", "")), snippet=_plain(r.get("content", ""))[:400])
                for r in rows if r.get("url")][:max_results]


KEYED_BACKENDS: dict[str, type[BaseWebSearchBackend]] = {"brave": BraveSearchBackend, "tavily": TavilySearchBackend}
SECRET_REF = "web_search_api_key"


def keyed_backend(ws: Any) -> BaseWebSearchBackend | None:
    """The search service the user set up in Settings (Brave or Tavily with their own key), else None."""
    try:
        from aether.life.store import life_store_for

        provider = str(life_store_for(ws).settings().get("web_search_provider") or "")
        cls = KEYED_BACKENDS.get(provider)
        key = ws.secret_store.get_secret(SECRET_REF) if cls else None
    except Exception:  # noqa: BLE001 - no keyed search, the free fallback is used
        return None
    return cls(key) if cls and key else None


class MockWebSearchBackend(BaseWebSearchBackend):
    """Deterministic mock backend for hermetic tests."""

    def __init__(self, predefined_results: list[WebSearchResult] | None = None, raise_error: Exception | None = None) -> None:
        self.predefined_results = predefined_results
        self.raise_error = raise_error

    def search(self, query: str, max_results: int = 5, timeout: float = 10.0) -> list[WebSearchResult]:
        if self.raise_error:
            raise self.raise_error

        if self.predefined_results is not None:
            return self.predefined_results[:max_results]

        return [
            WebSearchResult(
                title=f"Result for {query} - Source 1",
                url=f"https://example.com/search?q={urllib.parse.quote(query)}",
                snippet=f"Key facts and overview regarding {query} from official documentation.",
            ),
            WebSearchResult(
                title=f"Technical Guide - {query}",
                url=f"https://docs.example.org/{urllib.parse.quote(query)}",
                snippet=f"Detailed specifications, best practices, and API references for {query}.",
            ),
        ][:max_results]


def create_web_search_tool(
    backend: BaseWebSearchBackend | None = None,
    timeout: float = 10.0,
) -> Tool:
    """
    Create a Tool instance for web search.
    """
    engine = backend or DuckDuckGoSearchBackend(timeout=timeout)

    @tool(
        name="search_web",
        description="Search the web for up-to-date information, facts, articles, and documentation.",
        classification=ToolClassification.READ_ONLY,
    )
    def search_web(query: str, max_results: int = 5) -> str:
        clean_q = str(query).strip()
        if not clean_q:
            return "Errore: specificare una query di ricerca valida."

        try:
            results = engine.search(clean_q, max_results=max_results, timeout=timeout)
        except Exception as exc:
            return f"Impossibile completare la ricerca web per '{clean_q}': {exc}"

        if not results:
            return f"Nessun risultato trovato sul Web per la query: '{clean_q}'."

        output = [f"Risultati della ricerca Web per '{clean_q}' ({len(results)} fonti trovate):"]
        for idx, r in enumerate(results, 1):
            output.append(f"\n[{idx}] {r.title}\nURL: {r.url}\nEstratto: {r.snippet}")

        return "\n".join(output)

    return search_web
