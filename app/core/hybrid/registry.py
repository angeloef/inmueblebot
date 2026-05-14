"""Central registry: discover parsers by component name."""

from .base import HybridParser

_registry: dict[str, HybridParser] = {}


def register(component: str, parser: HybridParser) -> None:
    _registry[component] = parser


def get(component: str) -> HybridParser | None:
    """Get parser by component name. Returns None if not registered."""
    return _registry.get(component)


def list_parsers() -> dict[str, str]:
    """Show all registered parsers and their current strategy."""
    return {
        name: p.config.strategy
        for name, p in sorted(_registry.items())
    }
