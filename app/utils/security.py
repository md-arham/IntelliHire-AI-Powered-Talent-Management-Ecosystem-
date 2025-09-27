from datetime import datetime, timedelta
from typing import Optional, Dict, Any

from passlib.context import CryptContext
from authlib.jose import jwt
from app.utils.settings import settings
from datetime import timezone
from app.utils.logger_config import logger


pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


async def get_password_hash(password: str) -> str:
    """Hash a password using Argon2."""
    return pwd_context.hash(password)

async def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a stored hash."""
    return pwd_context.verify(plain_password, hashed_password)

# def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
#     """
#     Create a JWT access token with optional expiration.
    
#     Args:
#         data (dict): Data to encode into the token payload.
#         expires_delta (timedelta, optional): Custom token expiry duration.

#     Returns:
#         str: Encoded JWT token.
#     """
#     to_encode = data.copy()
#     expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
#     to_encode.update({"exp": expire})
    
#     encoded_jwt = jwt.encode(to_encode, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
#     return encoded_jwt

async def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    """
    Create a JWT access token with optional expiration.

    Args:
        data (dict): Data to encode into the token payload.
        expires_delta (timedelta, optional): Custom token expiry duration.

    Returns:
        str: Encoded JWT token.
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})

    header = {"alg": settings.JWT_ALGORITHM}
    token = jwt.encode(header, to_encode, settings.SECRET_KEY)
    logger.info(f"Token: {type(token.decode('utf-8'))}")
    return token.decode('utf-8')  # authlib returns bytes




