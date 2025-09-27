
from app.database.db import sessionLocal
from app.database.models import OfferLetterTemplate
from app.utils.settings import settings
from app.utils.logger_config import logger
import uuid
import os


def populate_templates():
    db = sessionLocal()
    os.makedirs(settings.OFFER_LETTER_TEMPLATES, exist_ok=True)
    logger.info(f"Offer Templates folder: {settings.OFFER_LETTER_TEMPLATES}")
    template_files = os.listdir(settings.OFFER_LETTER_TEMPLATES)
    for file in template_files:
        file_name = f"{settings.OFFER_LETTER_TEMPLATES}/{file}"
        exists = db.query(OfferLetterTemplate).filter_by(template_file=file_name).first()
        if not exists:
            logger.info(f"Adding file to db: {file_name}")
            template = OfferLetterTemplate(template_id=uuid.uuid4(), template_file=file_name)
            db.add(template)
    db.commit()
    db.close()