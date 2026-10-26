from __future__ import annotations

from urllib.parse import urlparse

from oss_kbdb.domain.models import SourceObject


class S3ObjectStore:
    def __init__(self, *, endpoint_url: str | None, region: str, access_key_id: str | None,
                 secret_access_key: str | None, addressing_style: str = "auto") -> None:
        import boto3
        config = None if addressing_style == "auto" else __import__("botocore.config", fromlist=["Config"]).Config(
            s3={"addressing_style": addressing_style})
        self._client = boto3.client("s3", endpoint_url=endpoint_url, region_name=region,
                                   aws_access_key_id=access_key_id, aws_secret_access_key=secret_access_key,
                                   config=config)

    @staticmethod
    def parse_uri(uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if parsed.scheme != "s3" or not parsed.netloc or not parsed.path.strip("/"):
            raise ValueError("URI deve ter formato s3://bucket/chave")
        return parsed.netloc, parsed.path.lstrip("/")

    def get(self, bucket: str, key: str) -> SourceObject:
        response = self._client.get_object(Bucket=bucket, Key=key)
        return SourceObject(bucket=bucket, key=key, content=response["Body"].read(),
                            etag=(response.get("ETag") or "").strip('"') or None,
                            content_type=response.get("ContentType"))
