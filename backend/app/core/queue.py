from arq import ArqRedis, create_pool
from arq.connections import RedisSettings

from app.core.config import get_settings

_pool: ArqRedis | None = None


async def get_queue() -> ArqRedis:
    global _pool
    if _pool is None:
        _pool = await create_pool(RedisSettings.from_dsn(get_settings().redis_url))
    return _pool


async def enqueue_processing(video_id: str, job_id: str) -> None:
    # _job_id makes enqueueing idempotent: the same processing job can't be queued twice.
    await (await get_queue()).enqueue_job("process_video", video_id, job_id, _job_id=f"process:{job_id}")
