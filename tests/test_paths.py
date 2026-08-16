from __future__ import annotations

from meshweave import paths


def test_data_dir_override_respected():
    # conftest redirige MESHWEAVE_DATA_DIR a un directorio temporal.
    d = paths.data_dir()
    assert d.is_absolute()


def test_subdirs_consistent():
    assert paths.config_dir().parent == paths.data_dir()
    assert paths.logs_dir().parent == paths.data_dir()
    assert paths.backups_dir().parent == paths.data_dir()
    assert paths.bin_dir().parent == paths.data_dir()
    assert paths.runtime_dir().parent == paths.data_dir()
    assert paths.secrets_path().parent == paths.data_dir()


def test_ensure_dirs_creates_all():
    paths.ensure_dirs()
    for d in (paths.data_dir(), paths.config_dir(), paths.logs_dir(),
              paths.state_dir(), paths.backups_dir(), paths.bin_dir(),
              paths.runtime_dir(), paths.user_data_dir()):
        assert d.is_dir()
