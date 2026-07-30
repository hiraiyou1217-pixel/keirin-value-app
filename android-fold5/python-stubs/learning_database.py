from __future__ import annotations

import os
from pathlib import Path


DATABASE_PATH = Path(
    os.environ.get(
        "KEIRIN_LEARNING_DATABASE",
        "keirin_learning.db",
    )
)
