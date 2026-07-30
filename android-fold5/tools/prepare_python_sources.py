from __future__ import annotations

import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ANDROID_ROOT = ROOT / "android-fold5"
OUTPUT = (
    ANDROID_ROOT
    / "app"
    / "src"
    / "main"
    / "python"
    / "generated_sources"
)
SOURCE_FILES = (
    "independent_learning_features.py",
    "lineup_from_comments.py",
    "portable_independent_model.py",
    "race_metadata.py",
)


def main() -> None:
    if OUTPUT.exists():
        shutil.rmtree(OUTPUT)

    OUTPUT.mkdir(parents=True)

    for filename in SOURCE_FILES:
        source = ROOT / filename

        if not source.exists():
            raise FileNotFoundError(source)

        shutil.copy2(
            source,
            OUTPUT / filename,
        )

    shutil.copy2(
        ANDROID_ROOT
        / "python-stubs"
        / "learning_database.py",
        OUTPUT / "learning_database.py",
    )
    print(
        f"Android Python sources: {OUTPUT}"
    )


if __name__ == "__main__":
    main()
