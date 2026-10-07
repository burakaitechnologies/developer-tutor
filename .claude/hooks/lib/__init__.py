"""lib - the shared modules of the tutor hooks (paths, clock, files, hook input and output, and more).

Why a package: the folder holds modules whose names equal standard-library modules (secrets, text,
tree). Importing them as `lib.secrets` can never pick up the wrong one. dispatch.py puts the hooks
folder first on sys.path before it imports anything from here.
Nothing runs at import time.
"""
from __future__ import annotations

import sys

sys.dont_write_bytecode = True
