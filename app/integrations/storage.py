import boto3
from botocore.exceptions import ClientError
from typing import Optional
from config.settings import get_settings

settings = get_settings()


class StorageClient:
    def __init__(self):
        self.bucket = settings.S3_BUCKET
        self.region = settings.S3_REGION
        self.client = boto3.client(
            "s3",
            region_name=self.region
        ) if self.bucket else None

    def upload_file(self, file_path: str, key: str) -> Optional[str]:
        if not self.client:
            return None
        try:
            self.client.upload_file(file_path, self.bucket, key)
            return f"https://{self.bucket}.s3.{self.region}.amazonaws.com/{key}"
        except ClientError:
            return None

    def get_presigned_url(self, key: str, expires: int = 3600) -> Optional[str]:
        if not self.client:
            return None
        try:
            return self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.bucket, "Key": key},
                ExpiresIn=expires
            )
        except ClientError:
            return None


storage_client = StorageClient()