import logging
from logging.handlers import RotatingFileHandler


def configure_logging(folder):
    folder.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(folder / "raphael.log", maxBytes=1000000, backupCount=2, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    logger = logging.getLogger("raphael")
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    logger.propagate = False
