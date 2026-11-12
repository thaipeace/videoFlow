"""HaizFlow desktop application and local media-processing pipeline."""

import json
import re
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python < 3.11 (e.g. macOS system python3)
    tomllib = None  # type: ignore[assignment]


def _application_version() -> str:
    # Distribution metadata can be stale in an editable build environment.
    # Read the running artifact, never the install root's original BUILD-INFO
    # or active pointer (which may already point to a different Core).
    if getattr(sys, "frozen", False):
        core = Path(sys.executable).absolute().parent
        build_info = core / "BUILD-INFO.json"
        if build_info.is_file():
            data = json.loads(build_info.read_text(encoding="utf-8"))
            value = data.get("version") if isinstance(data, dict) else None
            if (not isinstance(data, dict) or data.get("application") != "HaizFlow"
                    or not isinstance(value, str)
                    or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value)
                    or (core.parent.name == "versions" and core.name != value)):
                raise ValueError("Thông tin phiên bản bản cài đặt không hợp lệ.")
            return value
    # Source checkouts use canonical project metadata, even when an older
    # editable installation is present in the interpreter.
    pyproject = Path(__file__).resolve().parents[2] / "pyproject.toml"
    if not getattr(sys, "frozen", False) and pyproject.is_file():
        pyproject_text = pyproject.read_text(encoding="utf-8")
        if tomllib is not None:
            return tomllib.loads(pyproject_text)["project"]["version"]
        match = re.search(r'(?m)^version\s*=\s*"([^"]+)"', pyproject_text)
        if match:
            return match.group(1)
    try:
        return version("haizflow")
    except PackageNotFoundError:
        return "0.0.0+local"


__version__ = _application_version()
