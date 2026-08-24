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

from aether.tools.base import Tool
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
        result_blocks = re.findall(
            r'<div[^>]*class="[^"]*result\s+results_links[^"]*"[^>]*>(.*?)</div>\s*</div>',
            html_content,
            re.DOTALL,
        )

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
