"""Schema bootstrap and versioned migration scaffolding."""
from crm_db.core import (  # noqa: F401
    CURRENT_SCHEMA_VERSION,
    SCHEMA_MIGRATIONS,
    _backup_before_schema_migration,
    _init_schema,
    _recover_crashed_table_rebuild,
    _run_migration_script,
    _run_schema_migrations,
    _verify_and_swap_table,
)

__all__ = [
    "CURRENT_SCHEMA_VERSION",
    "SCHEMA_MIGRATIONS",
    "_backup_before_schema_migration",
    "_init_schema",
    "_recover_crashed_table_rebuild",
    "_run_migration_script",
    "_run_schema_migrations",
    "_verify_and_swap_table",
]

