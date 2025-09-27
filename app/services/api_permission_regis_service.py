from fastapi import FastAPI,Request, HTTPException
from fastapi.routing import APIRoute
from typing import List,Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.schemas.router_registration_schema import APIRegistration
from app.schemas.auth_schemas import UserRole
from app.services.rbac_auth_services import EnterpriseAuthorizationService
from app.database.db import get_db
from app.api.deps import get_auth_enforcer
from app.utils.logger_config import logger
from app.database.models.endpoint_registration_model import EndpointPermission
from app.utils.settings import settings
from authlib.jose import jwt
from colorama import Fore, Style


class PermissionService:
    @staticmethod
    async def register_permissions(
        req: APIRegistration,
        app: FastAPI,
        db: AsyncSession,
        enforcer: EnterpriseAuthorizationService,
    ) -> Dict[str, Any]:
        """
        TLDR: Registers permissions for API endpoints based on the provided request.
        Args:
            req (APIRegistration): The registration request containing role, domain, object, path (prefix or exact), 
                optional method, and effect ("allow" or "deny").
            app (FastAPI): The FastAPI application instance to inspect for matching routes.
            db (AsyncSession): The asynchronous database session for persisting permissions.
            enforcer (EnterpriseAuthorizationService): The authorization service used to manage policies.

        Returns:
            Dict[str, Any]: A summary message and details of registered permissions, including path, method, 
                and whether the policy was added to the enforcer.

        Raises:
            ValueError: If no matching routes are found for the given path and method.
        """
        matching_routes: List[APIRoute] = []

        logger.info(f"Checking routes for prefix or exact match: {req.path}")
        for route in app.routes:
            if not isinstance(route, APIRoute):
                continue

            # Exact match
            if req.path == route.path:
                if req.method:
                    if req.method in route.methods:
                        matching_routes.append(route)
                else:
                    matching_routes.append(route)

            # Prefix match
            elif route.path.startswith(req.path):
                if req.method:
                    if req.method in route.methods:
                        matching_routes.append(route)
                else:
                    matching_routes.append(route)
        if not matching_routes:
            raise ValueError("No matching routes found")

        results = []

        for route in matching_routes:
            for method in route.methods:
                if req.method and method != req.method:
                    continue

                # Add policy to Casbin
                added = await enforcer.add_policy(
                    req.role, req.domain, req.object, method, req.effect
                )

                # Save to DB
                permission = EndpointPermission(
                    role=req.role,
                    domain=req.domain,
                    object=req.object,
                    path=route.path,
                    method=method,
                    action=method,
                    effect=req.effect
                )
                db.add(permission)
                results.append({
                    "path": route.path,
                    "method": method,
                    "casbin_policy_added": added
                })

        await db.commit()

        return {
            "message": "Permissions registered",
            "details": results
        }
    

def extract_token_claims(token: str):
    """
        TLDR: Extract and decode claims from a JWT Bearer token.
        Args:
            token (str): The Authorization header value, expected to start with "Bearer ".

        Returns:
            dict: The decoded JWT claims.

        Raises:
            HTTPException: If the token format is invalid or the token is expired/invalid.
    """
     
    if not token.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Invalid token format")
    token = token[len("Bearer "):]
    try:
        return jwt.decode(token, settings.SECRET_KEY)
    except Exception:
        raise HTTPException(status_code=401, detail="Invalid or expired token")

async def check_permission(request: Request, db: AsyncSession, enforcer: EnterpriseAuthorizationService):
    # Skip certain public routes

    """
        TLDR: Check if the current request has the necessary permissions.

        This function:
        - Skips permission checks for public or excluded routes (e.g., authentication endpoints, docs).
        - Extracts the user's role from the JWT token in the Authorization header.
        - Grants all permissions to users with the "superadmin" role.
        - Checks if a matching permission exists in the database for the user's role, request path, and HTTP method.
        - Optionally, enforces the policy using the authorization enforcer.
        - Raises an HTTP 401 or 403 error if the user is unauthorized or lacks permission.

        Args:
            request (Request): The incoming HTTP request.
            db (AsyncSession): The asynchronous database session for permission lookup.
            enforcer (EnterpriseAuthorizationService): The authorization service for policy enforcement.

        Returns:
            bool: True if permission is granted, otherwise raises an exception.

        Raises:
            HTTPException: If the Authorization header is missing, the token is invalid, or permission is denied.
    """

    EXCLUDE_PATHS = ["/api/auth/token","/api/auth/verify-otp","/api/initialise/","/api/auth/register_user_rbac"]
    if request.url.path in EXCLUDE_PATHS:
        return True
    if request.url.path.startswith("/docs") or request.url.path.startswith("/open"):
        return True

    token = request.headers.get("Authorization")
    if not token:
        raise HTTPException(status_code=401, detail="Missing Authorization header")
    

    claims = extract_token_claims(token)
    role = claims.get("role")

    #Superadmin has all permissions
    if role == UserRole.superadmin.value:
        return True
    
    if request.method:
        method = request.method
    path = request.url.path

    results = await db.execute(
        select(EndpointPermission).filter_by(
            role=role,
            path=path,
            method=method
        )
    )
    permission = results.scalars().first()

    if not permission:
        raise HTTPException(status_code=403, detail="Permission denied")

    # if not enforcer.enforce(role, permission.domain, permission.object, method):
    #     raise HTTPException(status_code=403, detail="Permission denied")

    return True
