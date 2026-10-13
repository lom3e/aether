"""
Navigation helper for the browser tests.

The classic sidebar keeps the secondary destinations (Agents, Teams, Knowledge, Learning, Marketplace, ...) in a
hidden block of "compatibility alias elements for E2E tests" with stable ``data-testid="nav-<name>"`` attributes.
Hidden elements cannot receive a real mouse click, so the click event is dispatched on them directly.
"""
from __future__ import annotations


def nav(page, name: str) -> None:
    """Navigates to a sidebar destination by its ``data-testid="nav-<name>"`` alias."""
    page.locator(f"[data-testid='nav-{name}']").first.dispatch_event("click")
