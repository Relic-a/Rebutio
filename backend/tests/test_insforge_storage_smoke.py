import os
import uuid
import pytest

from backend.app.config import settings
from backend.app.services.media.storage import InsForgeMediaStorageService


@pytest.mark.asyncio
async def test_real_insforge_private_storage_smoke():
    """
    Real integration smoke test for InsForge private storage.
    Only executes when explicitly requested via INSFORGE_STORAGE_SMOKE_TEST=true
    or when a non-default INSFORGE_SERVICE_ROLE_KEY is configured.
    """
    has_explicit_flag = os.environ.get("INSFORGE_STORAGE_SMOKE_TEST", "").lower() in ("true", "1")
    service_role_key = settings.INSFORGE_SERVICE_ROLE_KEY or os.environ.get("INSFORGE_SERVICE_ROLE_KEY", "")

    if not (has_explicit_flag or (service_role_key and not service_role_key.startswith("dev-"))):
        pytest.skip("Skipping real InsForge storage smoke test: live credentials not provided.")

    storage = InsForgeMediaStorageService()
    test_id = uuid.uuid4().hex[:12]
    object_path = f"smoke_test/test_object_{test_id}.bin"
    payload = f"rebutio-live-smoke-test-payload-{test_id}".encode("utf-8")

    try:
        # 1. Upload
        uploaded = await storage._upload_to_insforge(object_path, payload, "application/octet-stream")
        assert uploaded is True, "Upload to InsForge private storage bucket failed"

        # 2. Download
        downloaded = await storage._download_from_insforge(object_path)
        assert downloaded is not None, "Failed to download uploaded object from InsForge storage"
        assert downloaded == payload, "Downloaded payload does not match uploaded payload"

    finally:
        # 3. Cleanup / Delete
        await storage._delete_from_insforge(object_path)
