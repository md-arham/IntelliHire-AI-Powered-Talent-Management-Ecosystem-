from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID
from sqlalchemy import select
from app.database.models.campusplacement_models import CampusDriveCompany


async def link_company_to_drive_if_not_exists(
    db: AsyncSession, company_id: UUID, drive_id: UUID
):
    """
    Ensures that a company is linked to a specific campus drive.
    If the association between the company and the drive does not already exist,
    a new record is inserted into the `campus_drive_companies` table.

    Args:
        db (AsyncSession): The database session.
        company_id (UUID): The UUID of the company to link.
        drive_id (UUID): The UUID of the campus drive to link the company to.

    Side Effects:
        - Adds a new `CampusDriveCompany` record if it doesn't already exist.
        - Does not commit the transaction (caller must handle commit).
    """
    exists = (
        (
            await db.execute(
                select(CampusDriveCompany).filter_by(
                    company_id=company_id, drive_id=drive_id
                )
            )
        )
        .scalars()
        .first()
    )

    if not exists:
        db.add(
            CampusDriveCompany(
                company_id=company_id,
                drive_id=drive_id,
            )
        )
