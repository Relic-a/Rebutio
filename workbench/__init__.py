import os
import sys

# Ensure repository root is on sys.path for backend and workbench imports
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

__version__ = "1.0.0"
