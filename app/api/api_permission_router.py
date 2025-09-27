from app.utils.get_app import get_app
from fastapi import APIRouter, FastAPI, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session
from app.schemas.router_registration_schema import APIRegistration
from app.schemas.auth_schemas import TokenData
from app.api.deps import get_current_user
from app.services.rbac_auth_services import EnterpriseAuthorizationService
from app.database.db import get_db
from app.api.deps import get_auth_enforcer
from app.services.api_permission_regis_service import PermissionService
router = APIRouter(prefix="/api/perm_regis", tags=["API Registration"])

@router.post("/register-permission")
async def  register_permission(
    req: APIRegistration,
    request: FastAPI = Depends(get_app),
    db: Session = Depends(get_db),
    token: TokenData = Depends(get_current_user),
    enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer),
)-> dict:
    """
        TLDR: Register a new permission for a role on a specified API endpoint.

        This endpoint allows administrators to register permissions for a role within a particular domain (tenant).
        The permission can be scoped to an exact API path or a path prefix, and may optionally specify an HTTP method (e.g., GET, POST).
        The registration process will:
        - Match the given path (and method, if provided) against the application's routes.
        - Add the permission policy to the authorization enforcer (e.g., Casbin).
        - Persist the permission in the database for auditing and enforcement.

        Args:
            req (APIRegistration): The permission registration request, including role, domain, object, path, optional method, and effect ("allow" or "deny").
            request (FastAPI): The FastAPI application instance, injected by dependency.
            db (Session): The database session, injected by dependency.
            token (TokenData): The current authenticated user's token data, injected by dependency.
            enforcer (EnterpriseAuthorizationService): The authorization enforcer instance, injected by dependency.

        Returns:
            dict: A message and details about the registered permission(s), including path, method, and policy addition status.

        Raises:
            HTTPException 404: If no matching routes are found for the specified path and method.

        Notes:
            - Only users with appropriate administrative privileges should be allowed to call this endpoint.
            - The effect can be "allow" or "deny", controlling whether the permission grants or blocks access.
            - Supports both exact and prefix-based path matching for flexible permission assignment.

    """

    try:
        response = await PermissionService.register_permissions(
            req=req,
            app=request,
            db=db,
            enforcer=enforcer
        )
        return response
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
