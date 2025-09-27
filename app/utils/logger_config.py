import logging

logger = logging.getLogger("resume_logger")
logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    logger.addHandler(handler)


isched_logger = logging.getLogger("interview_scheduler_logger")
isched_logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)
if not isched_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    isched_logger.addHandler(handler)

ol_logger = logging.getLogger("offer_letter_logger")
ol_logger.setLevel(logging.INFO)
logging.basicConfig(level=logging.INFO)
if not ol_logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    handler.setFormatter(formatter)
    ol_logger.addHandler(handler)
