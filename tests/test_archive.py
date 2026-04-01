import importlib

import pytest

SAMPLE_ACHIEVEMENT = {
    "title": "Corporate Houdini",
    "description": "New Achievement! You vanished for 120 minutes. Your Reward!",
    "reward": "Unlocked: Nobody noticed.",
}


# ---------------------------------------------------------------------------
# Local mode (SQLite) tests
# ---------------------------------------------------------------------------


@pytest.fixture
def local_archive(tmp_path, monkeypatch):
    """Redirect SQLite DB to a temp location."""
    db_path = tmp_path / "test.db"
    import config

    monkeypatch.setattr(config, "DB_PATH", db_path)
    monkeypatch.setattr(config, "STORAGE_MODE", "local")

    import archive

    archive._DB_INIT = False
    importlib.reload(archive)
    return db_path


def test_save_creates_db(local_archive):
    import archive

    entry = archive.save(SAMPLE_ACHIEVEMENT, trigger="took a long lunch")
    assert local_archive.exists()
    assert entry["id"] == 1
    assert entry["title"] == "Corporate Houdini"
    assert entry["trigger"] == "took a long lunch"
    assert "timestamp" in entry


def test_save_appends(local_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="first")
    archive.save(SAMPLE_ACHIEVEMENT, trigger="second")
    entries = archive.load_all()
    assert len(entries) == 2
    assert entries[0]["id"] == 1
    assert entries[1]["id"] == 2
    assert entries[0]["trigger"] == "first"
    assert entries[1]["trigger"] == "second"


def test_save_with_audio_files(local_archive):
    import archive

    files = ["/output/opener.mp3", "/output/desc.mp3"]
    entry = archive.save(SAMPLE_ACHIEVEMENT, audio_files=files)
    assert entry["audio_files"] == files


def test_save_without_trigger(local_archive):
    import archive

    entry = archive.save(SAMPLE_ACHIEVEMENT)
    assert entry["trigger"] is None


def test_load_all_empty(local_archive):
    import archive

    assert archive.load_all() == []


def test_load_all_returns_entries(local_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="a")
    archive.save(SAMPLE_ACHIEVEMENT, trigger="b")
    entries = archive.load_all()
    assert len(entries) == 2


def test_get_by_id(local_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="first")
    archive.save(SAMPLE_ACHIEVEMENT, trigger="second")
    entry = archive.get(2)
    assert entry is not None
    assert entry["trigger"] == "second"


def test_get_missing_id(local_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT)
    assert archive.get(999) is None


def test_archive_preserves_all_fields(local_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="test", audio_files=["/a.mp3"])
    loaded = archive.get(1)
    assert loaded["title"] == SAMPLE_ACHIEVEMENT["title"]
    assert loaded["description"] == SAMPLE_ACHIEVEMENT["description"]
    assert loaded["reward"] == SAMPLE_ACHIEVEMENT["reward"]
    assert loaded["trigger"] == "test"
    assert loaded["audio_files"] == ["/a.mp3"]


# ---------------------------------------------------------------------------
# Cloud mode (DynamoDB) tests
# ---------------------------------------------------------------------------


@pytest.fixture
def cloud_archive(monkeypatch):
    """Create a moto DynamoDB table for cloud mode testing."""
    import boto3
    from moto import mock_aws

    with mock_aws():
        monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
        monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
        monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")

        import config

        monkeypatch.setattr(config, "STORAGE_MODE", "cloud")
        monkeypatch.setattr(config, "DYNAMODB_TABLE", "test-achievements")

        import archive

        archive._DB_INIT = False
        importlib.reload(archive)

        # Create the table
        ddb = boto3.resource("dynamodb", region_name="us-east-1")
        ddb.create_table(
            TableName="test-achievements",
            KeySchema=[{"AttributeName": "id", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "id", "AttributeType": "N"}],
            BillingMode="PAY_PER_REQUEST",
        )

        yield


def test_cloud_save(cloud_archive):
    import archive

    entry = archive.save(SAMPLE_ACHIEVEMENT, trigger="cloud test")
    assert entry["id"] == 1
    assert entry["title"] == "Corporate Houdini"
    assert entry["trigger"] == "cloud test"


def test_cloud_save_auto_increment(cloud_archive):
    import archive

    e1 = archive.save(SAMPLE_ACHIEVEMENT, trigger="first")
    e2 = archive.save(SAMPLE_ACHIEVEMENT, trigger="second")
    assert e1["id"] == 1
    assert e2["id"] == 2


def test_cloud_load_all(cloud_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="a")
    archive.save(SAMPLE_ACHIEVEMENT, trigger="b")
    entries = archive.load_all()
    assert len(entries) == 2
    assert entries[0]["trigger"] == "a"
    assert entries[1]["trigger"] == "b"


def test_cloud_load_all_empty(cloud_archive):
    import archive

    assert archive.load_all() == []


def test_cloud_get_by_id(cloud_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, trigger="first")
    archive.save(SAMPLE_ACHIEVEMENT, trigger="second")
    entry = archive.get(2)
    assert entry is not None
    assert entry["trigger"] == "second"


def test_cloud_get_missing(cloud_archive):
    import archive

    assert archive.get(999) is None


def test_cloud_preserves_audio_files(cloud_archive):
    import archive

    archive.save(SAMPLE_ACHIEVEMENT, audio_files=["audio/opener.wav", "audio/reward.wav"])
    loaded = archive.get(1)
    assert loaded["audio_files"] == ["audio/opener.wav", "audio/reward.wav"]
