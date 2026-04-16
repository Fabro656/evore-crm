# models/__init__.py — Re-exports everything from _all.py
# This allows `from models import *` to keep working everywhere.
# The monolith _all.py can be gradually split into domain files.
from models._all import *  # noqa: F401,F403
from models._all import __all__  # noqa: F401
# Explicitly import underscore-prefixed functions used by routes
from models._all import _generar_sku, _migrate, init_db  # noqa: F401
