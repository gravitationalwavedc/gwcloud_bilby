import os
import sys

# Add bundle directory to path for scheduler imports
_bundle_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "bundle")
if _bundle_path not in sys.path:
    sys.path.insert(0, _bundle_path)
