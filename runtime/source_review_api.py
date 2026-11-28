"""Boundary for source API v1 and the still-deployed frozen reviewer pin.

Remove the legacy adapter only after the workflow pin is explicitly migrated and
its original frozen batches have been replayed. Never catch implementation errors.
"""
from importlib.util import find_spec

if find_spec('automation.research_api') is not None:
    from automation.research_api import (
        API_VERSION, ESPN, ScoreboardQueue, append, aware, regulation_row,
        certify_result, read_predictions, read_results,
    )
    if API_VERSION != 1:
        raise ValueError('unsupported source review API version')
    BACKEND = 'public-v1'
else:
    from automation.collector import ESPN, _ScoreboardQueue as ScoreboardQueue, append, aware, regulation_row
    from research_program.three_arm_review import (
        _certify as certify_result, _predictions as read_predictions, _results as read_results,
    )
    BACKEND = 'legacy-frozen-pin'
