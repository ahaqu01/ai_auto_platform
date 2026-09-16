from enum import StrEnum

from platform_api.common.errors import DomainError


class UploadSessionStatus(StrEnum):
    PENDING_UPLOAD = "PENDING_UPLOAD"
    UPLOADING = "UPLOADING"
    COMPLETING = "COMPLETING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"
    EXPIRED = "EXPIRED"
    FAILED = "FAILED"

    @property
    def is_terminal(self) -> bool:
        return self in {
            UploadSessionStatus.COMPLETED,
            UploadSessionStatus.ABORTED,
            UploadSessionStatus.EXPIRED,
            UploadSessionStatus.FAILED,
        }


class ArtifactStatus(StrEnum):
    VERIFYING = "VERIFYING"
    AVAILABLE = "AVAILABLE"
    QUARANTINED = "QUARANTINED"
    FAILED = "FAILED"
    DELETING = "DELETING"
    DELETED = "DELETED"


class IntegrityStatus(StrEnum):
    VERIFIED = "VERIFIED"
    MISMATCH = "MISMATCH"


class SecurityScanStatus(StrEnum):
    NOT_REQUIRED = "NOT_REQUIRED"
    PENDING = "PENDING"
    CLEAN = "CLEAN"
    BLOCKED = "BLOCKED"


ACTIVE_UPLOAD_STATUSES = {
    UploadSessionStatus.PENDING_UPLOAD,
    UploadSessionStatus.UPLOADING,
    UploadSessionStatus.COMPLETING,
}


def require_upload_session_cancellable(status: UploadSessionStatus) -> None:
    if status in {
        UploadSessionStatus.PENDING_UPLOAD,
        UploadSessionStatus.UPLOADING,
    }:
        return
    if status is UploadSessionStatus.ABORTED:
        return
    raise DomainError(
        "UPLOAD_STATE_CONFLICT",
        "当前上传会话状态不允许取消",
        409,
    )
