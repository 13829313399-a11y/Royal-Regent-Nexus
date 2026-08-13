import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from ai_guard_helpers import shared_guard_runtime  # noqa: F401


@pytest.fixture(autouse=True)
def restore_ai_app_import_graph(request: pytest.FixtureRequest):
    """Prevent env-specific app reloads from leaking across AI test modules."""

    if not request.node.path.name.startswith("test_ai_"):
        yield
        return
    original_modules = {
        module_name: module
        for module_name, module in sys.modules.items()
        if module_name == "app" or module_name.startswith("app.")
    }
    try:
        yield
    finally:
        graph_was_reloaded = any(
            sys.modules.get(module_name) is not module
            for module_name, module in original_modules.items()
        )
        if graph_was_reloaded:
            for module_name in list(sys.modules):
                if module_name == "app" or module_name.startswith("app."):
                    del sys.modules[module_name]
            sys.modules.update(original_modules)
