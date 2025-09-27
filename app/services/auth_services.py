from uuid import uuid4
from app.services.rbac_auth_services import AuthService
from fastapi import HTTPException
from typing import Dict,Union,List
import pyotp
from app.utils.logger_config import logger
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import smtplib

# from app.database.db import sessionLocal
from app.database.db import async_session_maker
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy import insert, delete
from passlib.context import CryptContext
from fastapi import HTTPException, status, UploadFile, BackgroundTasks
from app.services.resume_service import create_resume_version_profile
import aiosmtplib
from datetime import datetime, timedelta, timezone
from app.database.models import (
    User,
    Student,
    CampusPlacementOfficer,
    EmployerProfile,
    UserAuthProvider,
    Aspiration,
    OTPStore
    # ResumeVersion,
    # ResumeTypeEnum,
)
from app.schemas.auth_schemas import (
    StudentRegister,
    CampusOfficerRegister,
    EmployerRegister,
    UserRole,
    LoginRequest,
    LoginResponse,
    StudentRegistrationCollegeID,
)
from app.database.models.campusplacement_models import StudentBatch
from app.utils.logger_config import logger
import uuid
from starlette.datastructures import UploadFile as StarletteUploadFile
from io import BytesIO
from colorama import Fore,Style
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
from app.utils.settings import settings
from app.services.user_service import list_users
from app.utils.security import create_access_token


def get_or_create_user_via_provider(
    db: Session, provider: str, provider_user_id: str, email: str, full_name: str
):
    auth = (
        db.query(UserAuthProvider)
        .filter_by(provider=provider, provider_user_id=provider_user_id)
        .first()
    )

    if auth:
        return auth.user

    user = db.query(User).filter_by(email=email).first()

    if not user:
        user = User(
            user_id=uuid4(),
            email=email,
            full_name=full_name,
            password_hash=None,
            role=UserRole.Student,
            profile_img_path="",
        )
        db.add(user)
        db.flush()

    # Link the social login provider to this user
    auth = UserAuthProvider(
        id=uuid4(),
        user_id=user.user_id,
        provider=provider,
        provider_user_id=provider_user_id,
    )
    db.add(auth)
    db.commit()

    return user


# def register_user(db: Session, data: BaseUserRegister):
#     result = db.execute(select(User).where(User.email == data.email))
#     existing_user = result.scalar_one_or_none()
#     if existing_user:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="User with this email already exists",
#         )

#     password_hash = pwd_context.hash(data.password)
#     user = User(
#         full_name=data.full_name,
#         email=data.email,
#         password_hash=password_hash,
#         role=data.role,
#     )
#     try:
#         db.add(user)
#         db.flush()

#         if data.role == UserRole.student:
#             batch = StudentBatch(
#                 college_id=data.college_id,
#                 batch_year=data.batch_year,
#                 department=data.department,
#                 section=data.section,
#             )
#             db.add(batch)
#             db.flush()

#             student = Student(
#                 user_id=user.user_id,
#                 college_id=data.college_id,
#                 batch_id=batch.batch_id,
#                 email=data.email,
#             )
#             db.add(student)
#             db.flush()

#             for aspiration_text in data.aspirations or []:
#                 aspiration = Aspiration(
#                     student_id=student.student_id,
#                     aspiration_text=aspiration_text.strip(),
#                 )
#                 db.add(aspiration)

#         elif data.role == UserRole.campus_officer:
#             officer = CampusPlacementOfficer(
#                 user_id=user.user_id,
#                 college_id=data.college_id,
#                 contact_detail=getattr(data, "contact_detail", None),
#             )
#             db.add(officer)

#         elif data.role == UserRole.employer:
#             employer = EmployerProfile(
#                 user_id=user.user_id,
#                 company_id=data.company_id,
#             )
#             db.add(employer)
#         db.commit()
#         logger.info(f"role: {str(user.role)}\n\n2)No Str role:{user.role}")
#         return {
#             "message": f"{data.role.value.capitalize()} registered successfully",
#             "user_id": str(user.user_id),
#             "full_name": str(user.full_name),
#             "email": str(user.email),
#             "role": user.role.value,
#         }
#     except IntegrityError as e:
#         db.rollback()
#         logger.info(f"Integrity Issue because of {e}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Failed to register user due to data integrity issue",
#         )
#     except Exception as e:
#         db.rollback()
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Unexpected error: {str(e)}",
#         )


async def register_user(db: AsyncSession, data: Union[StudentRegister, CampusOfficerRegister, EmployerRegister]):
    result = await db.execute(select(User).where(User.email == data.email))
    existing_user = result.scalar_one_or_none()
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="User with this email already exists",
        )
    password_hash = pwd_context.hash(data.password)
    user = User(
        full_name=data.full_name,
        email=data.email,
        password_hash=password_hash,
        role=data.role,
    )
    try:
        db.add(user)
        await db.flush()

        if data.role == UserRole.student:
            batch = StudentBatch(
                college_id=data.college_id,
                batch_year=data.batch_year,
                department=data.department,
                section=data.section,
            )
            db.add(batch)
            await db.flush()

            student = Student(
                user_id=user.user_id,
                college_id=data.college_id,
                batch_id=batch.batch_id,
                email=data.email,
            )
            db.add(student)
            await db.flush()

            for aspiration_text in data.aspirations or []:
                aspiration = Aspiration(
                    student_id=student.student_id,
                    aspiration_text=aspiration_text.strip(),
                )
                db.add(aspiration)
        elif data.role == UserRole.campus_officer:
            officer = CampusPlacementOfficer(
                user_id=user.user_id,
                college_id=data.college_id,
                contact_detail=getattr(data, "contact_detail", None),
            )
            db.add(officer)

        elif data.role == UserRole.employer:
            employer = EmployerProfile(user_id=user.user_id, company_id=data.company_id)
            db.add(employer)

        await db.commit()

        return {
            "message": f"{data.role.value.capitalize()} registered successfully",
            "user_id": str(user.user_id),
            "full_name": str(user.full_name),
            "email": str(user.email),
            "role": user.role.value,
            "created_at": user.created_at.isoformat() if user.created_at else None,
        }
    except IntegrityError as e:
        await db.rollback()
        logger.info(f"Integrity Issue because of {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to register due to data integrity issue",
        )
    except Exception as e:
        await db.rollback()
        logger.info(f"Unexpected error: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Unexpected error: {str(e)}",
        )


def login_user(db: Session, data: LoginRequest):
    user = db.query(User).filter(User.email == data.email).first()

    if not user or not pwd_context.verify(data.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Email or Password"
        )
    return LoginResponse(
        user_id=user.user_id, full_name=user.full_name, role=user.role, email=user.email
    )


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


async def register_student_v2(
    form: StudentRegistrationCollegeID,
    resume_file: UploadFile,
    db: Session,
    background_tasks: BackgroundTasks,
):
    logger.info(form)
    if db.query(User).filter(User.email == form.email).first():
        raise HTTPException(status_code=400, detail="Email already registered")

    user = User(
        user_id=uuid.uuid4(),
        full_name=form.full_name,
        email=form.email,
        password_hash=hash_password(form.password),
        role="student",
    )
    db.add(user)
    db.flush()

    student = Student(
        student_id=uuid.uuid4(),
        user_id=user.user_id,
        college_id=form.college_id,
        email=form.email,
    )
    db.add(student)
    db.flush()

    for asp in form.aspirations:
        aspiration = Aspiration(
            aspiration_id=uuid.uuid4(),
            student_id=student.student_id,
            aspiration_text=asp,
        )
        db.add(aspiration)

    # Read the resume into memory before the response is returned
    resume_content = await resume_file.read()
    resume_bytesio = BytesIO(resume_content)

    # Schedule background task
    background_tasks.add_task(
        create_resume_version_profile,
        db=db,
        user_id=user.user_id,
        resume_type="Uploaded",
        resume_name=resume_file.filename,
        template_id=None,
        source_resume_id=None,
        file=StarletteUploadFile(filename=resume_file.filename, file=resume_bytesio),
    )

    db.commit()

    return {
        "message": "registered successfully",
        "user_id": str(user.user_id),
        "full_name": str(user.full_name),
        "email": str(user.email),
        "role": user.role.value,
    }



async def send_email(to_email: Union[str, List[str]], subject: str, body: str):
    if isinstance(to_email, str):
        recipients = [to_email]
    else:
        recipients = to_email
   
    # Determine content type
    html_content = is_html(body)

    # Build message
    msg = MIMEMultipart("alternative") if html_content else MIMEMultipart()
    msg["Subject"] = subject
    msg["From"] = settings.EMAIL_USER
    msg["To"] = ", ".join(recipients)

    if html_content:
        plain_fallback = "This is an HTML email. Please view it in an HTML-compatible client."
        msg.attach(MIMEText(plain_fallback, "plain"))
        msg.attach(MIMEText(body, "html"))
    else:
        msg.attach(MIMEText(body, "plain"))

    # Logging
    logger.info(Fore.YELLOW + f"Sending email to {to_email} with subject: {subject}")

    try:
        await aiosmtplib.send(
            msg,
            sender=settings.EMAIL_USER,
            recipients=recipients,
            hostname=settings.EMAIL_HOST,
            port=settings.EMAIL_PORT,
            start_tls=True,
            username=settings.EMAIL_USER,
            password=settings.EMAIL_PASSWORD,
        )
        logger.info(Fore.GREEN + f"Email successfully sent to {to_email}")
    except Exception as e:
        logger.error(Fore.RED + f"Email sending failed: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to send email: {str(e)}")


def is_html(content: str) -> bool:
    return "<html" in content.lower()

async def generate_otp_service(email: str, db: AsyncSession) -> str:
    logger.info(f"Generating OTP for {email}")

    result = await db.execute(select(User).filter(User.email == email))
    user = result.scalars().first()
    if not user:
        raise HTTPException(status_code=403, detail="User not found")

    secret = pyotp.random_base32()
    totp = pyotp.TOTP(secret, interval=300)
    otp = totp.now()

    # Removing old otps of the user
    await db.execute(delete(OTPStore).where(OTPStore.email == email))

    new_otp_entry = OTPStore(
        otp=otp,
        email=email,
        otp_secret=secret
    )
    db.add(new_otp_entry)
    await db.commit()

    db.commit()

    html_content = f"""
    <html>
        <body>
            <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 30px; border: 1px solid #ddd; border-radius: 10px; background-color: #ffffff; box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);">
                <h2 style="color: #007bff; text-align: center; margin-bottom: 20px;">🔒 Secure Verification Code</h2>
                <p style="font-size: 16px; color: #333; text-align: center;">Hello,</p>
                <p style="font-size: 16px; color: #555; text-align: center; margin-bottom: 20px;">
                    Use the verification code below to complete your sign-in process:
                </p>
                <div style="background: linear-gradient(135deg, #007bff, #0056b3); color: #007bff; padding: 15px 20px; border-radius: 8px; font-size: 26px; font-weight: bold; text-align: center; letter-spacing: 2px;">
                    {otp}
                </div>
                <p style="font-size: 16px; color: #555; text-align: center; margin-top: 20px;">
                    This code will expire in <strong>5 minutes</strong>. If you did not request this, please ignore this email.
                </p>
                <p style="font-size: 16px; color: #333; text-align: center; margin-top: 30px;">
                    Thank you for choosing our service!
                </p>
                <hr style="border: 0; height: 1px; background: #ddd; margin: 25px 0;">
                <p style="font-size: 14px; color: #888; text-align: center;">
                    Need help? <a href="mailto:support@aiden.com" style="color: #007bff; text-decoration: none;">Contact Support</a>
                </p>
            </div>
        </body>
    </html>
    """
    logger.info("Sending OTP email")
    await send_email(email, "Your Login OTP for AILab", html_content)
    return {"message": "OTP sent"}

async def verify_otp_service(otp: int, db: AsyncSession) -> dict:
    result = await db.execute(select(OTPStore).where(OTPStore.otp == str(otp)))
    otp_entry = result.scalars().first()

    if not otp_entry:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP")

    # OTP expiry logic
    if datetime.now(timezone.utc) - otp_entry.created_at > timedelta(minutes=5):
        await db.delete(otp_entry)
        await db.commit()
        raise HTTPException(status_code=400, detail="OTP has expired")

    # TOTP validation
    totp = pyotp.TOTP(otp_entry.otp_secret, interval=300)
    if not totp.verify(str(otp)):
        raise HTTPException(status_code=400, detail="Invalid OTP")

    # ✅ Issue token
    result = await db.execute(select(User).where(User.email == otp_entry.email))
    user = result.scalars().first()
    token = await AuthService(db).create_access_token_for_user(user)

    # ✅ Clean up used OTP
    await db.delete(otp_entry)
    await db.commit()

    return {
        "message": "OTP verified successfully",
        "access_token": token,
        "token_type": "bearer",
        "email": user.email,
        "role": user.role,
    }