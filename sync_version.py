"""
Sync version from pyproject.toml to manifest.json.

This script reads the version from pyproject.toml and checks or updates
the version in custom_components/tibber_prices/manifest.json. It is intended
to be run in a GitHub Action workflow to ensure the manifest version matches
the project version.
"""

import argparse
import json
import logging
import sys
import tomllib
from pathlib import Path
from typing import Any

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
_LOGGER = logging.getLogger(__name__)


def get_pyproject_version(pyproject_path: Path) -> str:
    """Read the version from pyproject.toml."""
    if not pyproject_path.exists():
        raise FileNotFoundError(f"{pyproject_path} does not exist")

    with pyproject_path.open("rb") as f:
        pyproject_data = tomllib.load(f)

    version = pyproject_data.get("project", {}).get("version")
    if not version:
        raise ValueError(f"Version not found in {pyproject_path}")

    return str(version)


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load the manifest.json file."""
    if not manifest_path.exists():
        raise FileNotFoundError(f"{manifest_path} does not exist")

    with manifest_path.open("r", encoding="utf-8") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Invalid JSON in {manifest_path}") from exc


def update_manifest_version(manifest_path: Path, version: str) -> None:
    """Update the version in manifest.json."""
    manifest_data = load_manifest(manifest_path)

    current_version = manifest_data.get("version")
    if current_version == version:
        _LOGGER.info("Manifest version is already %s", version)
        return

    manifest_data["version"] = version

    with manifest_path.open("w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2)
        f.write("\n")  # Ensure trailing newline

    _LOGGER.info(
        "Updated %s version from %s to %s", manifest_path, current_version, version
    )


def check_manifest_version(manifest_path: Path, version: str) -> bool:
    """Check if the version in manifest.json matches the given version."""
    manifest_data = load_manifest(manifest_path)

    current_version = manifest_data.get("version")
    if current_version == version:
        _LOGGER.info("Manifest version matches pyproject version (%s)", version)
        return True

    _LOGGER.error(
        "Manifest version mismatch: expected %s, found %s", version, current_version
    )
    return False


def main() -> int:
    """Execute the sync or check process."""
    parser = argparse.ArgumentParser(description="Sync pyproject version to manifest.")
    parser.add_argument(
        "--pyproject",
        type=Path,
        default=Path("pyproject.toml"),
        help="Path to pyproject.toml",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path("custom_components/tibber_prices/manifest.json"),
        help="Path to manifest.json",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Check if versions match instead of updating manifest.",
    )
    args = parser.parse_args()

    try:
        version = get_pyproject_version(args.pyproject)

        if args.check:
            is_valid = check_manifest_version(args.manifest, version)
            return 0 if is_valid else 1

        update_manifest_version(args.manifest, version)
        return 0

    except Exception as e:
        _LOGGER.error(str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
