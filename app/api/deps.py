from fastapi import Depends, HTTPException, status,Security
from fastapi.security import APIKeyHeader

oauth2_scheme = APIKeyHeader(name="Authorization")
# from jose import jwt, JWTError
from authlib.jose import jwt, JoseError
# from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.utils.logger_config import logger
from app.utils.settings import settings
from app.database.db import get_db
from app.schemas.auth_schemas import TokenData
from app.services.rbac_auth_services import AuthService, EnterpriseAuthorizationService

# OAuth2 scheme for token authentication

oauth2_scheme = APIKeyHeader(name="Authorization")

async def get_auth_service(db: AsyncSession = Depends(get_db)) -> AuthService:
    """
        TLDR: Dependency to get an instance of the AuthService.

        Args:
            db (AsyncSession): Asynchronous SQLAlchemy session.

        Returns:
            AuthService: An instance of the authentication service.
    """
    return AuthService(db)

async def get_auth_enforcer(db: AsyncSession = Depends(get_db)) -> EnterpriseAuthorizationService:
    """
        TLDR: Dependency to get an instance of the EnterpriseAuthorizationService.

        Args:
            db (AsyncSession): Asynchronous SQLAlchemy session.

        Returns:
            EnterpriseAuthorizationService: The authorization enforcer instance.
    """
    return EnterpriseAuthorizationService(db)

async def get_current_user(
    token: str = Security(oauth2_scheme),
    db: AsyncSession = Depends(get_db)
) -> TokenData:
    """
        TLDR: Dependency to extract and validate the current user from a JWT token.

        Args:
            token (str): Bearer token passed in the Authorization header.
            db (AsyncSession): Asynchronous SQLAlchemy session.

        Raises:
            HTTPException: If token is missing, invalid, or cannot be decoded.

        Returns:
            TokenData: Validated token payload containing username and user_id.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    if token.startswith("Bearer "):
        token = token[len("Bearer "):]
    try:
        claims = jwt.decode(token, settings.SECRET_KEY)
        # claims.validate()  # important: enforce 'exp', 'nbf', etc.

        username: str = claims.get("sub")
        user_id: str = claims.get("user_id")

        if username is None:
            raise credentials_exception
        # logger.info("Dependencies module loaded, thank you thank you")
        token_data = TokenData(username=username, user_id=user_id)
    except JoseError as e:
        logger.warning(f"JWT decode error: {e}")
        raise credentials_exception

    return token_data


