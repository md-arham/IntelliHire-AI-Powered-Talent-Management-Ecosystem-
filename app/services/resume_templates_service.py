from uuid import uuid4

from sqlalchemy.orm import Session

from app.database.models import ResumeTemplate
from app.schemas.resume_templates_schemas import (
    ResumeTemplateCreate,
    ResumeTemplateUpdate,
)


def create_template(db: Session, template_data: ResumeTemplateCreate):
    template = ResumeTemplate(
        template_id=uuid4(),
        name=template_data.name,
        preview_url=str(template_data.preview_url),
        is_active=template_data.is_active,
    )
    db.add(template)
    db.commit()
    db.refresh(template)
    return template


def get_all_templates(db: Session):
    return db.query(ResumeTemplate).order_by(ResumeTemplate.created_at.desc()).all()


def get_template_by_id(db: Session, template_id):
    return db.query(ResumeTemplate).filter_by(template_id=template_id).first()


def update_template(db: Session, template_id, update_data: ResumeTemplateUpdate):
    template = db.query(ResumeTemplate).filter_by(template_id=template_id).first()
    if not template:
        return None
    for field, value in update_data.model_dump(exclude_unset=True).items():
        setattr(template, field, value)
    db.commit()
    db.refresh(template)
    return template


def delete_template(db: Session, template_id):
    template = db.query(ResumeTemplate).filter_by(template_id=template_id).first()
    if not template:
        return False
    db.delete(template)
    db.commit()
    return True
