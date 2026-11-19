"""Optional LAN listener: only mobile assets and scoped inspection APIs."""
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from pydantic import SecretStr
from app.api.qc_mobile import router
from app.core.config import settings


@asynccontextmanager
async def lifespan(app):
    # The managed desktop API creates this private token for its QC sidecar.
    # Share that credential, without starting another sidecar or any workers.
    if not settings.qc_department_gateway_token.get_secret_value():
        path = Path(settings.qc_department_data_dir).resolve().parent / 'gateway-token'
        for _ in range(100):
            if path.is_file():
                token = path.read_text().strip()
                if len(token) >= 32:
                    settings.qc_department_gateway_token = SecretStr(token)
                    break
            await asyncio.sleep(.1)
        else:
            raise RuntimeError('Start the managed local QC service before the mobile listener')
    yield


app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
app.include_router(router)
