"""Check the data/ folder without starting the server.

    python -m backend.app.check_data [path/to/data]

Prints every problem with its file and field, and exits 1 if there is any.
"""

import sys
from pathlib import Path

from backend.app.config import Settings
from backend.app.services.catalog_loader import CatalogError, load_catalog


def main() -> int:
    data_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Settings.from_env().data_dir
    try:
        catalog = load_catalog(data_dir)
    except CatalogError as exc:
        print(f"{len(exc.problems)} problem(s) in {data_dir}:")
        for problem in exc.problems:
            print(f"  - {problem}")
        return 1
    print(
        f"OK: {len(catalog.components)} components, {len(catalog.scenarios)} scenario(s), "
        f"{len(catalog.events)} event(s), {len(catalog.sources)} source(s). "
        f"Version {catalog.catalog_version}, status '{catalog.data_status}'."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
