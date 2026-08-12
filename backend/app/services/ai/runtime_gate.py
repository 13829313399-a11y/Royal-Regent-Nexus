from pathlib import Path

from app.core.config import Settings

PRODUCTION_AI_RUNTIME_DISABLE_PATH = "/app/backend/control/ai.disabled"


def runtime_disable_control_configured(settings: Settings) -> bool:
    configured = settings.ai_runtime_disable_path.strip()
    if settings.app_env.strip().lower() in {"production", "prod"}:
        return configured == PRODUCTION_AI_RUNTIME_DISABLE_PATH
    return bool(configured)


def is_ai_runtime_disabled(settings: Settings) -> bool:
    """Check only marker existence; never read or log marker/path contents."""

    raw_path = settings.ai_runtime_disable_path.strip()
    if not raw_path:
        return False
    marker = Path(raw_path)
    try:
        marker.stat()
    except FileNotFoundError:
        return False
    except OSError:
        # A configured but unreadable control boundary fails closed.
        return True
    return True
