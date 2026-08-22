"""Actor identity for the Action Engine.

No separate rupee caps here: the Action Engine deliberately reuses
`app.auto_resolution.config.AutoResolutionConfig`'s bounds via
`app.auto_resolution.engine.policy_decision` rather than defining a
second set of thresholds — see DECISIONS.md for the reasoning. This
guarantees the downstream action can never be "more permissive" than
the auto-resolution safety policy it's built on.
"""
from __future__ import annotations

ACTOR = "system:finance_controller_action_engine"
