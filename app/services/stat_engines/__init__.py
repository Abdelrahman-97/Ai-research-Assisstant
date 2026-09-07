"""Audited statistical-test engines.

A library of deterministic, cited test functions the AI selects from (instead of
writing analysis code). Import the registry to discover or run engines:

    from app.services.stat_engines import registry
    registry.catalogue()                      # what's available (for the router/UI)
    registry.run_engine(key, df, params, fig_dir)   # run one
"""

from app.services.stat_engines.base import EngineError  # noqa: F401
from app.services.stat_engines.registry import REGISTRY, catalogue, run_engine  # noqa: F401
