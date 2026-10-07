"""Development and Windows Portable paths, independent of the working directory."""

import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RESOURCE_ROOT = Path(getattr(sys, '_MEIPASS', PROJECT_ROOT))
# Portable executable lives beside database/ and Images/. In development the
# source tree is the data root. Never silently fall back to AppData.
DATA_ROOT = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else PROJECT_ROOT
ACCESS_FILE = PROJECT_ROOT / "access source" / "Database2.accdb"
EXCEL_FILE = RESOURCE_ROOT / "access source" / "DatabaseStructure.xlsx"
UI_FILE = RESOURCE_ROOT / "ui" / "main_window.ui"
DATABASE_FILE = DATA_ROOT / "database" / "tender.db"
IMAGES_DIR = DATA_ROOT / "Images"
SETTINGS_FILE = DATA_ROOT / "config" / "settings.json"


def resource_path(relative_path):
    path = Path(relative_path)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError('Resource must be relative to the application resource root')
    return RESOURCE_ROOT / path


def resolve_image_path(relative_path, *, data_root=DATA_ROOT):
    """Resolve stored Images/... paths without depending on the working directory."""
    path = Path(relative_path)
    if path.is_absolute() or not path.parts or path.parts[0] != "Images":
        raise ValueError(f"图片路径必须位于 Images 目录: {relative_path!r}")
    images_dir = (Path(data_root) / "Images").resolve()
    resolved = (Path(data_root) / path).resolve()
    if resolved == images_dir or images_dir not in resolved.parents:
        raise ValueError(f"图片路径越过 Images 目录: {relative_path!r}")
    return resolved
