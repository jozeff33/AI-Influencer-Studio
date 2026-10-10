"""Run with: python -m app.story_worker (one instance only)."""
import logging
import os
import time
from .main import SessionLocal
from .story import worker_cycle

logging.basicConfig(level=logging.INFO)
logger=logging.getLogger(__name__)

if __name__=='__main__':
    delay=max(60,min(3600,int(os.getenv('STORY_WORKER_INTERVAL_SECONDS','600'))))
    logger.info('Autopilot worker started, polling every %s seconds',delay)
    while True:
        try:
            with SessionLocal() as session:worker_cycle(session)
        except Exception:
            logger.exception('Autopilot iteration failed')
        time.sleep(delay)
