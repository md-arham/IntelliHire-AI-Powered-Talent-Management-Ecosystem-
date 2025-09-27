import os
from uuid import UUID
from fastapi import UploadFile
import aiofiles
import aioboto3
from botocore.exceptions import NoCredentialsError
from app.utils.logger_config import logger
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.hackathon_models import Submission
from sqlalchemy import select, and_


async def save_file_locally(
    file: UploadFile,
    submission_id: UUID,
    upload_dir: str = "uploads/submissions",
) -> str:
    """
    Asynchronously save a ZIP file locally in the specified directory.

    Args:
        file (UploadFile): The uploaded ZIP file.
        submission_id (UUID): Unique identifier to name the file.
        upload_dir (str): Directory where file should be saved.

    Returns:
        str: Full path to the saved file.
    """
    os.makedirs(upload_dir, exist_ok=True)
    file_path = os.path.join(upload_dir, f"{submission_id}.zip")

    async with aiofiles.open(file_path, "wb") as out_file:
        while chunk := await file.read(1024 * 1024):
            await out_file.write(chunk)

    logger.info(f"File saved locally at {file_path}")
    return file_path


async def upload_file_to_s3(
    file: UploadFile,
    submission_id: UUID,
    bucket_name: str,
    s3_client: aioboto3.Session.client = None,
) -> str:
    """
    Asynchronously upload a ZIP file to an AWS S3 bucket.

    Args:
        file (UploadFile): The uploaded ZIP file.
        submission_id (UUID): Unique identifier to name the file in S3.
        bucket_name (str): Name of the S3 bucket.
        s3_client (optional): Reusable aioboto3 S3 client. If not provided, a new one is created.

    Returns:
        str: S3 URI of the uploaded file.

    Raises:
        Exception: If AWS credentials are missing or upload fails.
    """
    key = f"submissions/{submission_id}.zip"

    try:
        # Use provided client or create one
        if s3_client:
            await s3_client.upload_fileobj(file.file, bucket_name, key)
        else:
            session = aioboto3.Session()
            async with session.client("s3") as s3:
                await s3.upload_fileobj(file.file, bucket_name, key)

        s3_uri = f"s3://{bucket_name}/{key}"
        logger.info(f"File uploaded to S3: {s3_uri}")
        return s3_uri

    except NoCredentialsError:
        logger.error("AWS credentials not found.")
        raise Exception("AWS credentials not found.")


async def is_duplicate_submission(
    db: AsyncSession,
    team_id: UUID,
    hackathon_id: UUID,
    problem_statement_id: UUID,
) -> bool:
    result = await db.execute(
        select(Submission).where(
            and_(
                Submission.team_id == team_id,
                Submission.hackathon_id == hackathon_id,
                Submission.problem_statement_id == problem_statement_id,
            )
        )
    )
    return result.scalar_one_or_none() is not None
