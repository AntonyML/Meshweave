"""Los tests usan MESHWEAVE_DATA_DIR temporal (no tocan %ProgramData%)."""
from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def isolated_data_dir(monkeypatch: pytest.MonkeyPatch):
    tmp = tempfile.mkdtemp(prefix="meshweave-test-")
    monkeypatch.setenv("MESHWEAVE_DATA_DIR", os.path.join(tmp, "data"))
    monkeypatch.setenv("MESHWEAVE_USER_DATA_DIR", os.path.join(tmp, "user"))
    yield
