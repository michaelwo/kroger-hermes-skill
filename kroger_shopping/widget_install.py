"""Install and inspect the plugin-owned Kroger picker widget."""

import hashlib
import os
import tempfile
from pathlib import Path


WIDGET_FILENAME = "kroger-pick.mjs"


def bundled_widget_path() -> Path:
    return Path(__file__).resolve().parents[1] / "widgets" / WIDGET_FILENAME


def installed_widget_path() -> Path:
    home = Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser()
    return home / "tui-widgets" / WIDGET_FILENAME


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def install_widget() -> str:
    source = bundled_widget_path()
    if not source.is_file():
        return f"Kroger picker widget is missing from the plugin: `{source}`"

    destination = installed_widget_path()
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file() and _digest(destination) == _digest(source):
        return f"Kroger picker widget is already current: `{destination}`"

    action = "Updated" if destination.exists() else "Installed"
    with tempfile.NamedTemporaryFile(
        dir=destination.parent,
        prefix=f".{WIDGET_FILENAME}.",
        delete=False,
    ) as handle:
        temporary = Path(handle.name)
        handle.write(source.read_bytes())
        handle.flush()
        os.fsync(handle.fileno())

    try:
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return f"{action} Kroger picker widget: `{destination}`"


def widget_status() -> str:
    source = bundled_widget_path()
    destination = installed_widget_path()
    if not destination.is_file():
        return f"Kroger picker widget is not installed. Run `/kroger widget install`. Target: `{destination}`"
    if not source.is_file() or _digest(destination) != _digest(source):
        return f"Kroger picker widget needs an update. Run `/kroger widget install`. Target: `{destination}`"
    return f"Kroger picker widget is current: `{destination}`"


def remove_widget() -> str:
    destination = installed_widget_path()
    if not destination.exists():
        return f"Kroger picker widget is not installed: `{destination}`"
    destination.unlink()
    return f"Removed Kroger picker widget: `{destination}`"
