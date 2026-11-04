"""Schedule-only transport and persistence bounds; other imports stay at 20 MiB."""
from io import BytesIO

import pytest
from fastapi import HTTPException, UploadFile


@pytest.mark.parametrize("kind,limit", [("WEEKLY_SCHEDULE", 35), ("DELIVERY_NOTE", 20),
                                       ("INSPECTION_SCHEDULE", 20), (None, 20)])
@pytest.mark.parametrize("over", [False, True])
def test_reader_exact_limit_and_one_byte_over(kind, limit, over):
    from app.api.carton_procurement import _read_carton_upload
    size = limit * 1024 * 1024 + int(over)
    file = UploadFile(file=BytesIO(b"x" * size), filename="input.xlsx")
    if over:
        with pytest.raises(HTTPException) as error:
            _read_carton_upload(file, kind)
        assert error.value.status_code == 413
        assert str(limit) in error.value.detail
    else:
        assert len(_read_carton_upload(file, kind)) == size


def test_persistence_uses_same_schedule_limit_and_retains_other_bounds(monkeypatch):
    from app.services import carton_procurement as core, carton_schedule_coverage as coverage
    from app.services.customer_order_buzzbee import MAX_SCHEDULE_BYTES
    assert core.import_byte_limit("WEEKLY_SCHEDULE") == MAX_SCHEDULE_BYTES

    class ReachedAuthorization(Exception):
        pass

    def stop(*args):
        raise ReachedAuthorization()

    monkeypatch.setattr(coverage, "locked_import_actor", stop)
    file = UploadFile(file=BytesIO(), filename="input.xlsx")
    content = b"x" * MAX_SCHEDULE_BYTES
    with pytest.raises(ReachedAuthorization):
        core.create_import_batch(None, "huaxing", "WEEKLY_SCHEDULE", file, content, None, parsed_source={})
    for kind in ("DELIVERY_NOTE", "INSPECTION_SCHEDULE"):
        with pytest.raises(HTTPException) as error:
            core.create_import_batch(None, "huaxing", kind, file, content, None, parsed_source={})
        assert error.value.status_code == 413 and "20 MB" in error.value.detail
    with pytest.raises(HTTPException) as error:
        core.create_import_batch(None, "huaxing", "WEEKLY_SCHEDULE", file, content + b"x", None, parsed_source={})
    assert error.value.status_code == 413 and "35 MB" in error.value.detail
