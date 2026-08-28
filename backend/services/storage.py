import logging
from typing import BinaryIO
import boto3
from botocore.exceptions import ClientError
from config import Settings

logger = logging.getLogger(__name__)


class StorageService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.bucket_name = settings.s3_bucket_name
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key,
            aws_secret_access_key=settings.s3_secret_key,
        )

    def ensure_bucket(self) -> None:
        try:
            self.s3_client.head_bucket(Bucket=self.bucket_name)
        except ClientError:
            try:
                self.s3_client.create_bucket(Bucket=self.bucket_name)
                logger.info(f"Created bucket '{self.bucket_name}'")
            except Exception as exc:
                logger.error(f"Failed to create bucket '{self.bucket_name}': {exc}")
                raise

    def upload_fileobj(self, fileobj: BinaryIO, filename: str, content_type: str = "application/octet-stream") -> None:
        try:
            self.s3_client.upload_fileobj(
                fileobj,
                self.bucket_name,
                filename,
                ExtraArgs={"ContentType": content_type} if content_type else None,
            )
        except Exception as exc:
            logger.error(f"Upload failed for {filename}: {exc}")
            raise

    def download_file(self, filename: str, local_path: str) -> None:
        try:
            self.s3_client.download_file(self.bucket_name, filename, local_path)
        except Exception as exc:
            logger.error(f"Download failed for {filename}: {exc}")
            raise

    def delete_file(self, filename: str) -> None:
        try:
            self.s3_client.delete_object(Bucket=self.bucket_name, Key=filename)
        except Exception as exc:
            logger.warning(f"Failed to delete {filename} from S3: {exc}")
