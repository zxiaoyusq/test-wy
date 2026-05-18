from enum import Enum


class ModuleType(str, Enum):
    character = "character"
    video = "video"
    motion = "motion"
    facial = "facial"


class JobStatus(str, Enum):
    pending = "pending"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    cancelled = "cancelled"


class AssetType(str, Enum):
    image = "image"
    video = "video"
    model3d = "model3d"
    motion = "motion"
    facial = "facial"
    metadata = "metadata"
    log = "log"
    preview = "preview"
