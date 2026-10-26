import pytest

from oss_kbdb.adapters.s3 import S3ObjectStore


def test_parses_s3_uri():
    assert S3ObjectStore.parse_uri("s3://bucket/folder/file.pdf") == ("bucket", "folder/file.pdf")


@pytest.mark.parametrize("uri", ["https://bucket/key", "s3://bucket", "s3:///key"])
def test_rejects_invalid_s3_uri(uri):
    with pytest.raises(ValueError):
        S3ObjectStore.parse_uri(uri)
