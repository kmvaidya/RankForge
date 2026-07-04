# src/rankforge/features.py

"""Deployment-level feature flags.

RankForge is a generic rating platform, but individual deployments (e.g. a
personal instance with house rules) may want extras that would clutter a
stock install. Flags are declared here, enabled via the ``RANKFORGE_FEATURES``
environment variable (comma-separated, case-insensitive), and served to the
frontend through ``GET /config`` so one backend setting drives both layers.

Flags gate *exposure*, not correctness: core behavior (e.g. the rating
engine honoring ``match_metadata.weight``) always works; a flag only decides
whether the UI surfaces it.
"""

import logging
import os

logger = logging.getLogger(__name__)

# Every flag the codebase understands. Adding a feature = add its name here
# and gate the relevant UI/endpoint on it; unknown names in the env var are
# ignored with a warning so a typo can't silently enable/disable anything.
KNOWN_FEATURES: frozenset[str] = frozenset(
    {
        # Show a "match weight" input when recording a match, letting special
        # events count for more (or less) than a normal game.
        "match_weights",
        # The live session runner (courts, up-next bench queue, fair
        # rotation) — a Session page for running a night of play.
        "session_mode",
    }
)


def enabled_features() -> list[str]:
    """The sorted list of enabled feature flags for this deployment.

    Reads ``RANKFORGE_FEATURES`` on every call so tests (and container
    restarts) pick up changes without import-order tricks.
    """
    raw = os.getenv("RANKFORGE_FEATURES", "")
    requested = {token.strip().lower() for token in raw.split(",") if token.strip()}
    unknown = requested - KNOWN_FEATURES
    if unknown:
        logger.warning(
            "Ignoring unknown feature flag(s) in RANKFORGE_FEATURES: %s",
            ", ".join(sorted(unknown)),
        )
    return sorted(requested & KNOWN_FEATURES)
