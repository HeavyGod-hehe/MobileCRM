"""CRM data layer package — split for human navigation.

Implementation lives in ``crm_db.core``. Domain modules re-export related
symbols so readers can open a focused file:

- ``conn`` — connections, paths, sessions
- ``schema`` — schema init / constants surface
- ``migrations`` — ``_migrate_*`` / ``SCHEMA_MIGRATIONS``
- ``ledger`` — ledger_links and purchase/sale posting
- ``phones`` — phone CRUD, expenses, returns
- ``accounts`` — accounts, cash book, banks
- ``reports`` — dashboard / today / month / closing
- ``backup_undo`` — backup, restore, undo helpers

``import database as db`` still works via the Source/database.py facade
(an alias of ``crm_db.core``).
"""
