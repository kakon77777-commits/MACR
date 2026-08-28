from __future__ import annotations

from importlib.resources import files


_ASSETS = frozenset({"index.html", "app.js", "style.css"})


def read_asset(name: str) -> bytes:
    if name not in _ASSETS:
        raise KeyError("Direct UI asset is not registered")
    return files(__package__).joinpath(name).read_bytes()
