from fastapi import HTTPException
import pytest

from app.core.config import Settings, settings
from app.services import carton_asset_access as access


def test_asset_flags_load_from_backend_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv('CARTON_ASSET_V1_ENABLED', raising=False)
    monkeypatch.delenv('CARTON_ASSET_V1_WRITES_ENABLED', raising=False)
    env = tmp_path / '.env'
    env.write_text('CARTON_ASSET_V1_ENABLED=true\nCARTON_ASSET_V1_WRITES_ENABLED=true\n')
    configured = Settings(_env_file=env)
    monkeypatch.setattr(settings, 'carton_asset_v1_enabled', configured.carton_asset_v1_enabled)
    monkeypatch.setattr(settings, 'carton_asset_v1_writes_enabled', configured.carton_asset_v1_writes_enabled)
    assert access.enabled()
    access.writes()
    monkeypatch.setenv('CARTON_ASSET_V1_WRITES_ENABLED', 'false')
    with pytest.raises(HTTPException) as error:
        access.writes()
    assert error.value.status_code == 403
    monkeypatch.setenv('CARTON_ASSET_V1_ENABLED', 'false')
    assert not access.enabled()
