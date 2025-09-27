from uuid import UUID

from fastapi import APIRouter, Depends, Form, File, UploadFile

from sqlalchemy.ext.asyncio import AsyncSession

from app.database.db import get_db

from app.schemas.user_schemas import (
    ProfileUpdateSchema,
    UserResponse,
)
from app.schemas.auth_schemas import TokenData
from app.services import user_service
from app.utils.logger_config import logger
from app.api.deps import get_current_user
router = APIRouter(prefix="/api/users", tags=["Users"])


@router.get("/get_user/{user_id}", response_model=UserResponse)
async def get_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a user by their UUID.

    Args:
        user_id (UUID): The unique identifier of the user.
        db (AsyncSession): The database session dependency.

    Returns:
        UserResponse: The user details.

    Raises:
        HTTPException: If the user is not found.
    """
    return await user_service.get_user_by_id(db, user_id)


@router.get("/get_users/", response_model=list[UserResponse])
async def list_users(db: AsyncSession = Depends(get_db)):
    """
    Retrieve all users from the database.

    Args:
        db (AsyncSession): Asynchronous database session.

    Returns:
        list[UserResponse]: A list of all user records.
    """
    return await user_service.list_users(db)


@router.delete("/delete_user/{user_id}", status_code=204)
async def delete_user(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Delete a user and their associated profile based on role.

    Args:
        user_id (UUID): Unique identifier of the user to delete.
        db (AsyncSession): Asynchronous database session.

    Returns:
        None

    Raises:
        HTTPException: If the user does not exist or deletion fails.
    """
    await user_service.delete_user(db, user_id)
    logger.info(f"User deleted: {user_id}")


@router.post("/get_user_profile/{user_id}", status_code=200)
async def get_user_profile(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve structured resume data for a given student user.

    Args:
        user_id (UUID): The UUID of the user (Student).
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: A structured resume representation of the user profile.

    Raises:
        HTTPException: If the student or personal info is not found.
    """
    return await user_service.get_structured_resume_data(user_id, db)


@router.post("/update_profile/{user_id}")
async def update_profile(
    user_id: UUID, profile_data: ProfileUpdateSchema, db: AsyncSession = Depends(get_db),token:TokenData = Depends(get_current_user)
):
    return await user_service.update_user_profile(user_id, db, profile_data)

@router.get("/profile_strength/{user_id}")
async def profile_strength(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Calculate and return the profile strength score for a specific user.

    Args:
        user_id (UUID): The unique identifier of the user whose profile strength is being calculated.
        db (AsyncSession): Asynchronous database session dependency.

    Returns:
        dict: A dictionary containing the profile strength score and a list of any missing fields 
              required to improve the profile, or an error message if the profile cannot be scored.
    """
    return await user_service.get_profile_strength_score(user_id, db)


@router.post("/upload-profile-image")
async def upload_profile_image(
    user_id: UUID = Form(...),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload a profile image for a user.

    Args:
        user_id (UUID): The UUID of the user.
        file (UploadFile): The uploaded image file.
        db (AsyncSession): Asynchronous database session.

    Returns:
        dict: Contains user_id and image save path.

    Raises:
        HTTPException: If the user is not found or file type is invalid.
    """
    return await user_service.upload_profile_image_service(
        user_id=user_id, file=file, db=db
    )


@router.post("/get_profile_img/{user_id}")
async def get_profile_img(user_id: UUID, db: AsyncSession = Depends(get_db)):
    """
    Retrieve a user's profile image as a file response.

    Args:
        user_id (UUID): UUID of the user.
        db (AsyncSession): Asynchronous database session.

    Returns:
        FileResponse: The image file response.

    Raises:
        HTTPException: If the user or image is not found.
    """
    return await user_service.get_profile_image(user_id, db)
