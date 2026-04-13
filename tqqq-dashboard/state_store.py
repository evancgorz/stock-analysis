from __future__ import annotations

import json
from pathlib import Path
from typing import Any


STATE_FILE = Path(__file__).resolve().parent / "user_state.json"


def load_app_state() -> dict[str, Any]:
    if not STATE_FILE.exists():
        return {"last_page": "play_the_dip", "pages": {}}

    try:
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {"last_page": "play_the_dip", "pages": {}}


def load_page_state(page_key: str, defaults: dict[str, Any]) -> dict[str, Any]:
    state = load_app_state()
    page_state = state.get("pages", {}).get(page_key, {})
    return {**defaults, **page_state}


def save_page_state(page_key: str, values: dict[str, Any], *, last_page: str) -> None:
    state = load_app_state()
    state.setdefault("pages", {})
    state["pages"][page_key] = values
    state["last_page"] = last_page
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
