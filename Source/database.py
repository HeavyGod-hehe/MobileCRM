"""Compatibility facade for the CRM data layer.

Implementation lives in ``crm_db.core``. Prefer reading domain modules under
``crm_db/`` (``ledger``, ``phones``, ``accounts``, ``reports``, …) when
navigating the code. All existing ``import database as db`` call sites keep
working unchanged.
"""
from crm_db.core import *  # noqa: F403
