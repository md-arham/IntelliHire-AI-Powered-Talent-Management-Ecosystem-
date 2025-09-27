from sqlalchemy import Column, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy import Enum, String, TIMESTAMP
from sqlalchemy.sql import func

from app.database.db import Base
from app.database.models.enums_models import OfferLetterEnum

import uuid

class OfferLetter(Base):
    __tablename__ = "offer_letters"
    
    letter_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id = Column(UUID(as_uuid=True), ForeignKey("students.student_id", ondelete="CASCADE"))
    job_id = Column(UUID(as_uuid=True), ForeignKey("job_postings.job_id", ondelete="CASCADE"))
    letter_file = Column(String)
    status = Column(Enum(OfferLetterEnum, name='letter_status', create_type=True, default=OfferLetterEnum.Unsigned, nullable=False))
    offered_on = Column(TIMESTAMP, server_default=func.now())

class OfferLetterTemplate(Base):
    __tablename__ = "offer_letter_templates"
    
    template_id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    template_file = Column(String)

