# noqa: D104
"""Top-level package for uab_scholars."""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["ScholarsClient"]


def __getattr__(name):  # type: ignore[override]
    if name == "ScholarsClient":
        from .client import ScholarsClient

        return ScholarsClient
    raise AttributeError(name) 