import enum


class Role(enum.StrEnum):
    USER = "user"
    MODERATOR = "moderator"
    ADMIN = "admin"


class Visibility(enum.StrEnum):
    PUBLIC = "public"
    UNLISTED = "unlisted"  # by link only, not in feeds and search
    PRIVATE = "private"  # owner + users with an explicit grant


class VideoStatus(enum.StrEnum):
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class ModerationState(enum.StrEnum):
    ACTIVE = "active"
    HIDDEN = "hidden"


class FileKind(enum.StrEnum):
    ORIGINAL = "original"
    RENDITION = "rendition"


class UploadStatus(enum.StrEnum):
    PENDING = "pending"
    COMPLETED = "completed"
    ABORTED = "aborted"


class JobStatus(enum.StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class ReportReason(enum.StrEnum):
    SPAM = "spam"
    VIOLENCE = "violence"
    HATE = "hate"
    SEXUAL = "sexual"
    COPYRIGHT = "copyright"
    MISLEADING = "misleading"
    OTHER = "other"


class ReportStatus(enum.StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"  # action taken
    DISMISSED = "dismissed"  # no violation


class ModerationActionType(enum.StrEnum):
    HIDE_VIDEO = "hide_video"
    RESTORE_VIDEO = "restore_video"
    DELETE_COMMENT = "delete_comment"
    DISMISS_REPORT = "dismiss_report"
    BAN_USER = "ban_user"
    UNBAN_USER = "unban_user"
    CHANGE_ROLE = "change_role"
