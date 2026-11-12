import logging
import os
import tempfile

from arq import cron
from arq.connections import RedisSettings

from app.core.config import get_settings
from app.worker.tasks import MAX_TRIES, cleanup_stale_uploads, process_video

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


async def startup(ctx: dict) -> None:
    """Fail loudly if the scratch dir is not usable: tempfile would silently fall back to /tmp."""
    wanted = os.environ.get("TMPDIR")
    actual = tempfile.gettempdir()
    if wanted and os.path.realpath(actual) != os.path.realpath(wanted):
        raise RuntimeError(f"TMPDIR={wanted} is not writable, tempfile uses {actual}")
    logging.getLogger("vidora.worker").info("worker started, scratch dir %s", actual)


class WorkerSettings:
    """arq worker: same image and code as the API, separate process.

    max_jobs=2: ffmpeg is CPU-bound, more parallel jobs on a small VM only slow everything down.
    """

    functions = [process_video]
    on_startup = startup
    cron_jobs = [cron(cleanup_stale_uploads, minute=7, run_at_startup=False)]
    redis_settings = RedisSettings.from_dsn(get_settings().redis_url)
    max_jobs = 2
    max_tries = MAX_TRIES
    job_timeout = 3 * 60 * 60
    keep_result = 3600
    health_check_interval = 20
