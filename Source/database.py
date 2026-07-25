"""Compatibility facade for the CRM data layer.

Implementation lives in ``crm_db.core``. Prefer reading domain modules under
``crm_db/`` (``ledger``, ``phones``, ``accounts``, ``reports``, …) when
navigating the code.

This module is an alias of ``crm_db.core`` so ``import database as db`` keeps
the full API (including underscore helpers) and so test patches like
``db.CURRENT_SCHEMA_VERSION = …`` affect the real implementation.
"""
from __future__ import annotations

import sys
from importlib import import_module

_core = import_module("crm_db.core")
# importlib returns whatever is in sys.modules after exec_module — replacing
# this entry makes ``import database`` yield the core module object itself.
sys.modules[__name__] = _core
