"""V4 quality guard — KA0 stub re-exports V3 guard unchanged.

KA1+ will add evidence-aware gating and sub-goal verdict logic.
"""

# ponytail: identical guard logic as V3 for KA0; KA1 adds sub-goal verdict
from app.routers.v3.guard import (  # noqa: F401
    CRITICAL_ACTIONS,
    GuardResult,
    JudgeVerdict,
    run_guard,
    should_judge,
)
