from __future__ import annotations

import base64
import hashlib
from pathlib import Path

import boto3
from botocore.client import BaseClient
from botocore.exceptions import ClientError


class S3DocumentStore:
    """
    BizAid 문서 원본을 AWS S3에 저장하고 검증하는 저장소.

    문서의 content SHA-256을 object key로 사용한다.
    따라서 같은 내용의 문서는 여러 relation에서 참조하더라도
    S3에는 하나의 object만 저장한다.
    """

    def __init__(
            self,
            bucket: str,
            region: str,
            prefix: str = "biz-aid/documents",
            client: BaseClient | None = None,
    ) -> None:
        if not bucket.strip():
            raise ValueError("S3 bucket must not be empty")

        if not region.strip():
            raise ValueError("AWS region must not be empty")

        self.bucket = bucket
        self.region = region
        self.prefix = prefix.strip("/")

        # Credential을 코드에서 직접 관리하지 않는다.
        # 로컬에서는 AWS CLI login,
        # EC2에서는 IAM Role 등 boto3 기본 credential chain을 사용한다.
        self.client = client or boto3.client(
            "s3",
            region_name=region,
        )

    def object_key(
            self,
            sha256_hex: str,
    ) -> str:
        """
        SHA-256을 기반으로 immutable S3 object key를 만든다.

        예:
        biz-aid/documents/sha256/ab/cd/abcdef...
        """
        self._validate_sha256(sha256_hex)

        return (
            f"{self.prefix}/sha256/"
            f"{sha256_hex[:2]}/"
            f"{sha256_hex[2:4]}/"
            f"{sha256_hex}"
        )

    def put(
            self,
            file_path: Path,
            sha256_hex: str,
            byte_size: int,
    ) -> str:
        """
        문서를 content-addressed object로 안전하게 저장한다.

        같은 SHA의 object가 이미 존재하면 덮어쓰지 않고
        기존 object의 size/checksum을 검증한 뒤 재사용한다.
        """
        return self.put_key(file_path, self.object_key(sha256_hex), sha256_hex, byte_size)

    def put_key(self, file_path: Path, key: str, sha256_hex: str, byte_size: int,
                content_type: str = "application/octet-stream") -> str:
        """검증된 임의 key에 immutable object를 저장한다. content-addressed 원문과 parsed artifact가 함께 쓴다."""
        self._validate_sha256(sha256_hex)
        self._validate_key(key)
        if not file_path.is_file():
            raise FileNotFoundError(file_path)
        actual_size = file_path.stat().st_size
        if actual_size != byte_size:
            raise ValueError(f"file size mismatch: expected={byte_size}, actual={actual_size}")
        actual_sha256 = self._calculate_file_sha256(file_path)
        if actual_sha256 != sha256_hex:
            raise ValueError(f"file sha256 mismatch: expected={sha256_hex}, actual={actual_sha256}")

        # 이미 같은 SHA object가 존재하면 덮어쓰지 않는다.
        if self.exists_key(key):
            if not self.verify_key(key, sha256_hex, byte_size):
                raise RuntimeError(
                    "existing S3 object failed "
                    "integrity verification"
                )

            return key

        checksum_base64 = (
            self._sha256_hex_to_base64(
                sha256_hex
            )
        )

        try:
            with file_path.open("rb") as file_obj:
                self.client.put_object(
                    Bucket=self.bucket,
                    Key=key,
                    Body=file_obj,
                    ContentLength=byte_size,
                    ContentType=content_type,
                    ChecksumSHA256=checksum_base64,

                    # 동시에 같은 SHA object를 생성하려는 경우에도
                    # 기존 object를 덮어쓰지 않는다.
                    IfNoneMatch="*",
                )

        except ClientError as exc:
            status_code = (
                exc.response
                .get("ResponseMetadata", {})
                .get("HTTPStatusCode")
            )

            # 다른 실행이 먼저 같은 object를 생성했다면
            # 해당 object를 검증한 뒤 재사용한다.
            if status_code == 412:
                if self.verify_key(key, sha256_hex, byte_size):
                    return key

            raise

        # PUT 성공 응답만 믿지 않고
        # S3 metadata를 다시 확인한다.
        if not self.verify_key(key, sha256_hex, byte_size):
            raise RuntimeError(
                "uploaded S3 object failed "
                "integrity verification"
            )

        return key

    def exists(
            self,
            sha256_hex: str,
    ) -> bool:
        """
        SHA에 대응하는 S3 object가 존재하는지 확인한다.
        """
        return self.exists_key(self.object_key(sha256_hex))

    def exists_key(self, key: str) -> bool:
        """고정된 object key의 존재를 확인한다."""
        self._validate_key(key)

        try:
            self.client.head_object(
                Bucket=self.bucket,
                Key=key,
            )

            return True

        except ClientError as exc:
            status_code = (
                exc.response
                .get("ResponseMetadata", {})
                .get("HTTPStatusCode")
            )

            if status_code == 404:
                return False

            raise

    def verify(
            self,
            sha256_hex: str,
            byte_size: int,
    ) -> bool:
        """
        S3 object의 크기와 SHA-256 checksum metadata를 검증한다.
        """
        self._validate_sha256(sha256_hex)

        return self.verify_key(self.object_key(sha256_hex), sha256_hex, byte_size)

    def verify_key(self, key: str, sha256_hex: str, byte_size: int) -> bool:
        """고정된 key object의 크기와 SHA-256 checksum metadata를 검증한다."""
        self._validate_sha256(sha256_hex)
        self._validate_key(key)

        try:
            response = self.client.head_object(
                Bucket=self.bucket,
                Key=key,
                ChecksumMode="ENABLED",
            )

        except ClientError as exc:
            status_code = (
                exc.response
                .get("ResponseMetadata", {})
                .get("HTTPStatusCode")
            )

            if status_code == 404:
                return False

            raise

        actual_size = response.get(
            "ContentLength"
        )

        if actual_size != byte_size:
            return False

        expected_checksum = (
            self._sha256_hex_to_base64(
                sha256_hex
            )
        )

        actual_checksum = response.get(
            "ChecksumSHA256"
        )

        if actual_checksum != expected_checksum:
            return False

        return True

    def read(
            self,
            sha256_hex: str,
            byte_size: int,
            max_bytes: int = 100 * 1024 * 1024,
    ) -> bytes:
        """
        S3 object의 실제 byte를 읽고
        size와 SHA-256을 다시 검증한다.

        Parser나 Quality Gate가 DB metadata와 HEAD 결과만
        신뢰하지 않고 실제 저장된 byte를 확인할 때 사용한다.
        """
        self._validate_sha256(sha256_hex)

        if byte_size <= 0:
            raise ValueError(
                "byte_size must be positive"
            )

        if byte_size > max_bytes:
            raise ValueError(
                "S3 object exceeds configured read limit"
            )

        return self.read_key(self.object_key(sha256_hex), sha256_hex, byte_size, max_bytes)

    def read_key(self, key: str, sha256_hex: str, byte_size: int,
                 max_bytes: int = 100 * 1024 * 1024) -> bytes:
        """고정된 key의 실제 byte를 읽어 size, SHA-256과 S3 checksum metadata를 검증한다."""
        self._validate_sha256(sha256_hex)
        self._validate_key(key)

        if byte_size <= 0:
            raise ValueError("byte_size must be positive")

        if byte_size > max_bytes:
            raise ValueError("S3 object exceeds configured read limit")

        response = self.client.get_object(
            Bucket=self.bucket,
            Key=key,
            ChecksumMode="ENABLED",
        )

        body = response["Body"]

        try:
            raw = body.read(
                max_bytes + 1
            )
        finally:
            body.close()

        if len(raw) > max_bytes:
            raise RuntimeError(
                "S3 object exceeds configured read limit"
            )

        if len(raw) != byte_size:
            raise RuntimeError(
                f"S3 object size mismatch: "
                f"expected={byte_size}, "
                f"actual={len(raw)}"
            )

        actual_sha256 = hashlib.sha256(
            raw
        ).hexdigest()

        if actual_sha256 != sha256_hex:
            raise RuntimeError(
                "S3 object SHA-256 mismatch"
            )

        expected_checksum = (
            self._sha256_hex_to_base64(
                sha256_hex
            )
        )

        actual_checksum = response.get(
            "ChecksumSHA256"
        )

        # S3가 checksum metadata를 반환한 경우에는
        # 해당 값까지 함께 검증한다.
        if (
                actual_checksum is not None
                and actual_checksum
                != expected_checksum
        ):
            raise RuntimeError(
                "S3 object checksum metadata mismatch"
            )

        return raw

    @staticmethod
    def _calculate_file_sha256(
            file_path: Path,
    ) -> str:
        """
        파일 전체를 읽어 SHA-256을 계산한다.
        """
        sha256 = hashlib.sha256()

        with file_path.open("rb") as file_obj:
            while True:
                chunk = file_obj.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                sha256.update(chunk)

        return sha256.hexdigest()

    @staticmethod
    def _sha256_hex_to_base64(
            sha256_hex: str,
    ) -> str:
        """
        hex SHA-256을 S3 API가 사용하는
        Base64 checksum 형식으로 변환한다.
        """
        return base64.b64encode(
            bytes.fromhex(sha256_hex)
        ).decode("ascii")

    @staticmethod
    def _validate_sha256(
            sha256_hex: str,
    ) -> None:
        """
        잘못된 SHA가 object key로 사용되는 것을 막는다.
        """
        if len(sha256_hex) != 64:
            raise ValueError(
                "SHA-256 must be exactly "
                "64 hex characters"
            )

        try:
            bytes.fromhex(
                sha256_hex
            )

        except ValueError as exc:
            raise ValueError(
                "SHA-256 must contain only "
                "hexadecimal characters"
            ) from exc

    @staticmethod
    def _validate_key(key: str) -> None:
        parts = key.split("/")
        if not key or key.startswith("/") or any(part in ("", ".", "..") for part in parts):
            raise ValueError("unsafe S3 object key")
