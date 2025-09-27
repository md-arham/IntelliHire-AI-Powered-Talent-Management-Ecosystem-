from typing import List, Optional, Union, Any
from authlib.integrations.starlette_client import OAuth
from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    File,
    BackgroundTasks,
    UploadFile,
    Form,
    status
)
from pydantic import EmailStr
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.requests import Request
from uuid import UUID
from app.database.db import get_db
from app.services.rbac_auth_services import AuthService, EnterpriseAuthorizationService
from app.services.notification_service import notification_service, NotificationType
from app.services import auth_services, notification_service
from fastapi.security import OAuth2PasswordRequestForm
from app.schemas.user_schemas import (
    LoginRequest, 
    # UserResponsewithActivity,
    UserWithPassword,
    UserResponse,
)
from app.schemas.auth_schemas import (
    UserRegistrationUnion,
    LoginRequest,
    OTPRequest,
    LoginOutput,
)
from app.services import notification_service
from app.utils.settings import settings
from app.utils.logger_config import logger
from app.services.auth_services import register_user
from app.api.deps import get_auth_service,get_auth_enforcer


router = APIRouter(prefix="/api/auth", tags=["Auth"])
# oauth = OAuth()

# oauth.register(
#     name="google",
#     client_id=settings.GOOGLE_CLIENT_ID,
#     client_secret=settings.GOOGLE_CLIENT_SECRET,
#     server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
#     # access_token_url="https://oauth2.googleapis.com/token",
#     access_token_params=None,
#     # authorize_url="https://accounts.google.com/o/oauth2/v2/auth",
#     authorize_params={"access_type": "offline", "prompt": "consent"},
#     api_base_url="https://www.googleapis.com/oauth2/v2/",
#     client_kwargs={"scope": "openid email profile"},
# )


# @router.post("/register/student")
# async def register_student(
#     data: StudentRegister,
#     background_tasks: BackgroundTasks,  # Add this parameter
#     db: AsyncSession = Depends(get_db),
# ):
#     # Call your existing service
#     result = await auth_services.register_user(db, data)

#     # Add background task for email notification after successful registration
#     # try:
#     #     background_tasks.add_task(
#     #         notification_service.send_notification,
#     #         db,
#     #         result["user_id"],  # Get user_id from the service result
#     #         NotificationType.LOGIN_WELCOME,  # You'll need to add this type
#     #     )
#     # except Exception as e:
#     #     logger.error(
#     #         f"Failed to start registration notification task because: {str(e)}"
#     # )

#     return result


# @router.post("/register/campus_officer")
# def register_campus_officer(data: CampusOfficerRegister, db: Session = Depends(get_db)):
#     return auth_services.register_user(db, data)


# @router.post("/register/employer")
# def register_employer(data: EmployerRegister, db: Session = Depends(get_db)):
#     return auth_services.register_user(db, data)


# @router.post("/login")
# def login(data: LoginRequest, db: Session = Depends(get_db)):
#     return auth_services.login_user(db, data)


# @router.get("/google/login")
# async def google_login(request: Request):
#     redirect_uri = settings.GOOGLE_REDIRECT_URI
#     return await oauth.google.authorize_redirect(request, redirect_uri)


# @router.get("/google/callback")
# async def google_callback(request: Request, db: Session = Depends(get_db)):
#     token = await oauth.google.authorize_access_token(request)
#     logger.info(f"Token Data: {token}")
#     # user_info = await oauth.google.parse_id_token(request, token)
#     resp = await oauth.google.get("userinfo", token=token)
#     try:
#         logger.info(f"User Status: {resp.status_code}")
#         logger.info(f"User Text: {resp.text}")
#         user_info = resp.json()
#     except Exception as e:
#         logger.error(f"An Error Occured: {e}")
#         raise HTTPException(status_code=500, detail="An error Occured")
#     if not user_info:
#         raise HTTPException(status_code=401, detail="Failed to retrieve Google Profile")

#     email = user_info["email"]
#     full_name = user_info.get("name")
#     google_id = user_info.get("sub")

#     user = auth_services.get_or_create_user_via_provider(
#         db=db,
#         provider="google",
#         provider_user_id=google_id,
#         email=email,
#         full_name=full_name,
#     )

#     return {
#         "user_id": str(user.user_id),
#         "email": user.email,
#         "full_name": user.full_name,
#         "role": user.role,
#     }


# @router.post("/v2/register/student")
# async def student_register(
#     background_tasks: BackgroundTasks,
#     form: StudentRegistrationCollegeID = Depends(),
#     resume_file: UploadFile = File(...),
#     db: Session = Depends(get_db),
# ):
#     return await register_student_v2(
#         form=form,
#         resume_file=resume_file,
#         db=db,
#         background_tasks=background_tasks,
#     )



@router.post("/token")
async def login_rbac(
    form_data: OAuth2PasswordRequestForm = Depends(),
    # form_data: LoginRequestRBAC,
    auth_service: AuthService = Depends(get_auth_service),
    db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Authenticate a user via OAuth2 and initiate OTP authentication.

    Accepts user credentials (email and password) and, if valid, triggers
    the generation of a one-time password (OTP) for two-factor authentication.

    Request Body:
        OAuth2PasswordRequestForm (fields: username as email, password)

    Returns:
        dict: A message indicating that authentication succeeded and OTP is required.
    
    Raises:
        HTTPException: If authentication fails due to incorrect credentials.
    """
    user = await auth_service.authenticate_user(form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    await auth_services.generate_otp_service(form_data.username,db)
    return {"message": "Successfully authenticated, now time to authenticate otp"}




@router.post("/register_user_rbac", response_model=UserResponse)
async def user_registration(
    user_create: UserRegistrationUnion ,
    db: AsyncSession = Depends(get_db),
    auth_enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer)
) -> Any:
    """
    Register a new user with role-based access control (RBAC).
    
    Creates a new user account with role-specific data (student, campus_officer, or employer),
    and assigns the role in the authorization system.

    Request Body:
        One of: StudentRegister, CampusOfficerRegister, or EmployerRegister

    Returns:
        UserResponse: The created user's details

    Raises:
        HTTPException: If user exists, data is invalid, or role mismatch
    """
    logger.info(f"Checking user input: {user_create}")

    try:
        user = await register_user(db,user_create)
        domain = "tenant:system"
        logger.info(f"User created: {type(user_create.role)} with email {type(user_create.email)}")
        
        # Adding a role definition of the user in the casbin rule table.
        if not await auth_enforcer.has_role_for_user((user_create.email), user_create.role.value,domain=domain):
            await auth_enforcer.add_role_for_user(user_create.email, user_create.role.value,domain=domain)
            logger.info(f"Assigned role '{user_create.role}' to '{user_create.full_name}' in domain '{domain}'")
        else:
            logger.info(f"Role '{user_create.role}' already assigned to '{user_create.full_name}' in domain '{domain}'")    

        return user
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )




@router.post("/verify-otp",response_model=LoginOutput)
async def verify_otp(data: OTPRequest, db: AsyncSession = Depends(get_db)):
    """
        Verify a user's one-time password (OTP) for authentication.

        Checks whether the provided OTP is valid and, if so, returns an access token
        and user information.

        Request Body:
            OTPRequest (fields: otp)

        Returns:
            LoginOutput: Authentication result including message, access token, token type, email, and role.

        Raises:
            HTTPException: If the OTP is invalid or expired.
    """
    otp = int(data.otp)
    resp = await auth_services.verify_otp_service(otp,db)
    return resp
    
    