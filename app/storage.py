"""
Video storage abstraction layer for RacePilot.
Supports both local filesystem and Cloudflare R2 storage.
"""

import os
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from typing import BinaryIO, Optional
from datetime import datetime, timedelta


class VideoStorage:
    """Abstract video storage interface"""

    def __init__(self):
        self.storage_type = os.getenv("VIDEO_STORAGE_TYPE", "local")

        if self.storage_type == "r2":
            self._init_r2()
        else:
            self._init_local()

    def _init_local(self):
        """Initialize local filesystem storage"""
        self.upload_dir = os.getenv("VIDEO_UPLOAD_DIR", "/data/videos")
        os.makedirs(self.upload_dir, exist_ok=True)
        print(f"[VideoStorage] Using local storage: {self.upload_dir}")

    def _init_r2(self):
        """Initialize Cloudflare R2 storage"""
        self.r2_endpoint = os.getenv("R2_ENDPOINT_URL")
        self.r2_access_key = os.getenv("R2_ACCESS_KEY_ID")
        self.r2_secret_key = os.getenv("R2_SECRET_ACCESS_KEY")
        self.r2_bucket = os.getenv("R2_BUCKET_NAME", "racepilot-videos")
        self.r2_public_url = os.getenv("R2_PUBLIC_URL")  # Optional: Custom domain

        if not all([self.r2_endpoint, self.r2_access_key, self.r2_secret_key]):
            raise ValueError(
                "R2 storage requires R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, "
                "and R2_SECRET_ACCESS_KEY environment variables"
            )

        # Initialize boto3 S3 client for R2
        self.s3_client = boto3.client(
            's3',
            endpoint_url=self.r2_endpoint,
            aws_access_key_id=self.r2_access_key,
            aws_secret_access_key=self.r2_secret_key,
            config=Config(
                signature_version='s3v4',
                s3={'addressing_style': 'path'}
            ),
            region_name='auto'  # R2 uses 'auto' for region
        )

        # Verify bucket exists
        try:
            self.s3_client.head_bucket(Bucket=self.r2_bucket)
            print(f"[VideoStorage] Using R2 storage: bucket={self.r2_bucket}")
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == '404':
                print(f"[VideoStorage] Creating R2 bucket: {self.r2_bucket}")
                self.s3_client.create_bucket(Bucket=self.r2_bucket)
            else:
                raise

    def upload_file(
        self,
        file_obj: BinaryIO,
        filename: str,
        user_id: int,
        session_id: int,
        content_type: str = "video/mp4"
    ) -> tuple[str, int]:
        """
        Upload a video file to storage.

        Files are organized by user: videos/user-{user_id}/session-{session_id}_{timestamp}.ext
        This allows easy browsing of all videos by user.

        Returns:
            tuple: (storage_path, file_size)
        """
        # Generate unique key/path organized by user
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        ext = os.path.splitext(filename)[1].lower()
        user_folder = f"user-{user_id}"
        video_filename = f"session-{session_id}_{timestamp}{ext}"

        if self.storage_type == "r2":
            return self._upload_to_r2(file_obj, video_filename, content_type, user_folder)
        else:
            return self._upload_to_local(file_obj, video_filename, user_folder)

    def _upload_to_local(
        self,
        file_obj: BinaryIO,
        filename: str,
        user_folder: str = ""
    ) -> tuple[str, int]:
        """Upload to local filesystem"""
        # Create user folder if needed
        if user_folder:
            user_dir = os.path.join(self.upload_dir, user_folder)
            os.makedirs(user_dir, exist_ok=True)
            file_path = os.path.join(user_dir, filename)
        else:
            file_path = os.path.join(self.upload_dir, filename)

        file_size = 0
        with open(file_path, "wb") as f:
            while chunk := file_obj.read(1024 * 1024):  # 1MB chunks
                file_size += len(chunk)
                f.write(chunk)

        return file_path, file_size

    def _upload_to_r2(
        self,
        file_obj: BinaryIO,
        filename: str,
        content_type: str,
        user_folder: str = ""
    ) -> tuple[str, int]:
        """Upload to Cloudflare R2"""
        # Organize by user folder: videos/user-{user_id}/session-{session_id}_{timestamp}.mp4
        if user_folder:
            key = f"videos/{user_folder}/{filename}"
        else:
            key = f"videos/{filename}"

        # Calculate file size
        file_obj.seek(0, 2)  # Seek to end
        file_size = file_obj.tell()
        file_obj.seek(0)  # Seek back to beginning

        # Upload to R2
        self.s3_client.upload_fileobj(
            file_obj,
            self.r2_bucket,
            key,
            ExtraArgs={
                'ContentType': content_type,
                'CacheControl': 'public, max-age=31536000',  # Cache for 1 year
            }
        )

        return key, file_size

    def get_url(self, storage_path: str, expires_in: int = 3600) -> str:
        """
        Get a URL for accessing the video.

        Args:
            storage_path: The path/key returned from upload_file
            expires_in: Seconds until URL expires (for R2 presigned URLs)

        Returns:
            URL to access the video
        """
        if self.storage_type == "r2":
            # If using custom domain (public R2 bucket), return public URL
            if self.r2_public_url:
                return f"{self.r2_public_url}/{storage_path}"

            # Otherwise, generate presigned URL
            return self.s3_client.generate_presigned_url(
                'get_object',
                Params={
                    'Bucket': self.r2_bucket,
                    'Key': storage_path
                },
                ExpiresIn=expires_in
            )
        else:
            # Local storage - return relative path for API endpoint
            filename = os.path.basename(storage_path)
            return f"/videos/stream/{filename}"

    def delete_file(self, storage_path: str) -> bool:
        """
        Delete a video file from storage.

        Returns:
            True if successful, False otherwise
        """
        try:
            if self.storage_type == "r2":
                self.s3_client.delete_object(
                    Bucket=self.r2_bucket,
                    Key=storage_path
                )
            else:
                if os.path.exists(storage_path):
                    os.remove(storage_path)
            return True
        except Exception as e:
            print(f"[VideoStorage] Failed to delete {storage_path}: {e}")
            return False

    def get_file_stream(self, storage_path: str):
        """
        Get a file stream for local storage (used for streaming endpoint).
        Only works with local storage.
        """
        if self.storage_type == "r2":
            raise ValueError("get_file_stream() only works with local storage. Use get_url() for R2.")

        if not os.path.exists(storage_path):
            raise FileNotFoundError(f"Video file not found: {storage_path}")

        return storage_path  # Return path for FileResponse


# Singleton instance
_storage_instance: Optional[VideoStorage] = None


def get_video_storage() -> VideoStorage:
    """Get or create the video storage singleton"""
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = VideoStorage()
    return _storage_instance
