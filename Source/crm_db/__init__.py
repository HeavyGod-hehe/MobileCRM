"""CRM data layer package — split for human navigation.

Implementation lives in ``crm_db.core``. Domain modules re-export related
symbols so readers can open a focused file. ``import database as db`` still
works via the Source/database.py facade.
"""
from crm_db.core import *  # noqa: F403
