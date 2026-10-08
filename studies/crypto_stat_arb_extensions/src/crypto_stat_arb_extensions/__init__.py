"""Isolated non-commercial crypto research with immutable baseline dependencies."""
from pathlib import Path
import sys

# Exact copied baseline APIs are shipped so the ZIP remains self-contained.
# Their original files and public interfaces are not edited.
_vendor = str(Path(__file__).resolve().parent / '_vendor')
if _vendor not in sys.path:
    sys.path.insert(0, _vendor)
__version__ = '0.1.0'
