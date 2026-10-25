"""Configuration for pytest tests."""

import sys
import os

# Add project root to PYTHONPATH so tests can import db, guard, server
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if project_root not in sys.path:
    sys.path.insert(0, project_root)
