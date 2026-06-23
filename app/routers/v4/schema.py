"""V4 engine output schema — KA0 stub re-exports V3 schema unchanged.

KA1+ will extend this with sub-goal and evidence fields.
"""

# ponytail: same schema as V3 for KA0; KA1 adds sub_goals and evidence_refs
from app.routers.v3.schema import (  # noqa: F401
    TURN_JSON_SCHEMA,
    TURN_SCHEMA_NAME,
)
