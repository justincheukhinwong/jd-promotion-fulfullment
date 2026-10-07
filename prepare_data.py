"""Extract the five required JD inputs from a locally held Archive.zip."""
from pathlib import Path
from zipfile import ZipFile
import argparse
import shutil
from src.config import DATA_DIR, FILES


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?", type=Path, default=DATA_DIR / "Archive.zip")
    args = parser.parse_args()
    with ZipFile(args.archive) as archive:
        for filename in FILES.values():
            matches = [name for name in archive.namelist()
                       if Path(name).name == filename and not name.startswith("__MACOSX/")]
            if len(matches) != 1:
                raise ValueError(f"Expected exactly one {filename} in the archive.")
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            with archive.open(matches[0]) as source, (DATA_DIR / filename).open("wb") as target:
                shutil.copyfileobj(source, target)
            print(f"Prepared data/raw/{filename}")


if __name__ == "__main__":
    main()
