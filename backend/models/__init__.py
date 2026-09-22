"""Re-exports Base + models so Alembic's `target_metadata` sees the full schema.

Plan 04 extends this file with the other six entities.
"""

from .base import Base
from .report import Report

__all__ = ["Base", "Report"]
