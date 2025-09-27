# from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.db import get_db
from app.services.rbac_auth_services import AuthService, EnterpriseAuthorizationService
from app.schemas.user_schemas import UserWithPassword
from fastapi import APIRouter, Depends
from app.utils.logger_config import logger
from app.schemas.auth_schemas import UserRole
from app.services.user_service import create_user


router = APIRouter(tags=["Initalization"], prefix="/api/initialise")


@router.post("/")
async def initialize_superadmin(db: AsyncSession = Depends(get_db)) -> bool:
    """
        Initialize the system with a default superadmin user and permissions.
        This endpoint creates a superadmin user with predefined credentials if one does not already exist.
        Args:
            db (AsyncSession): Database session dependency injected by FastAPI.

        Returns:
            bool: True if initialization is successful.

        Raises:
            HTTPException: If any database or authorization operation fails.

        Note:
            - This endpoint is intended for one-time system initialization.
            - The superadmin credentials are hardcoded and should be changed in production.
    """

    auth_service = AuthService(db)
    enforcer = EnterpriseAuthorizationService(db)

    # Adding superadmin user vakesy credentials;)
    username = "Vakesy"
    password = "vakesy123"
    email = "aashish.james@aidenai.com"
    role = UserRole.superadmin.value
    domain = "tenant:system"

    user_data = {
        "email": email,
        "full_name": username,
        "password": password,
        "role": role,
        "student_profile": None,
        "employer_profile": None,
    }
    # Assign 'superadmin' role in 'system' domain

    # Adding vakesy to database
    try:
        user = await create_user(user_data=user_data, profile_image=None, db=db)
        logger.info(" Created superadmin user")
    except ValueError:
        user = await auth_service.get_user_by_username(username)
        logger.info(" Superadmin user already exists")


    if not await enforcer.has_role_for_user(email, role, domain):
        await enforcer.add_role_for_user(email, role, domain)
        logger.info(f"Assigned role '{role}' to '{username}' in domain '{domain}'")
    else:
        logger.info(f"Role '{role}' already assigned to '{username}' in domain '{domain}'")


    # Step 3: Add wildcard policy (can be customized)
    allow_all_policy = [role, domain, "*", "*", "allow"]
    # allow_all_policy = [role, domain, "policy", "delete", "allow"]
    # allow_all_policy = [role, domain, "policy", "update", "allow"]
    # allow_all_policy = [role, domain, "policy", "read", "allow"]

    if not await enforcer.has_policy(*allow_all_policy):
        await enforcer.add_policy(*allow_all_policy)
        logger.info("Added superadmin wildcard policy")
    else:
        logger.info("Superadmin policy already exists")

    return True