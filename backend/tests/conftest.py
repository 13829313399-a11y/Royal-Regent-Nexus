import sys
from pathlib import Path

import pytest

BACKEND_DIR = Path(__file__).resolve().parents[1]

if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))


@pytest.fixture(autouse=True)
def preserve_application_module_identity():
    """Contain environment-driven app reloads within the test that requests them.

    Collected tests retain references to exception classes, models and settings.
    A replacement app module graph must not leak into their subsequent lazy imports.
    Ordinary lazy imports remain cached when no original module was replaced.
    """
    original = {
        name: module for name, module in sys.modules.items()
        if name == "app" or name.startswith("app.")
    }
    yield
    if any(sys.modules.get(name) is not module for name, module in original.items()):
        for name in list(sys.modules):
            if name == "app" or name.startswith("app."):
                del sys.modules[name]
        sys.modules.update(original)
