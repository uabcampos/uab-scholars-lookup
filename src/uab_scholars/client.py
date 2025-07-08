"""uab_scholars.client

Thin wrapper around the legacy `Tools` class, providing a stable public
interface `ScholarsClient` that will be expanded as we refactor.
"""
from __future__ import annotations

from uab_scholars_tool_fully_optimized_and_renamed import Tools as _Tools


class ScholarsClient(_Tools):
    """Public client for the Scholars@UAB REST API.

    Currently inherits all methods from the internal `_Tools` implementation
    to preserve behaviour while we refactor the codebase into a proper
    package.  Downstream code should depend on *this* class instead of the
    legacy module.
    """

    # Any additional convenience wrappers can be added here in future

    pass 