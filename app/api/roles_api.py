from typing import Any, List
from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.auth_schemas import TokenData
from app.schemas.role_schemas import RoleAssignment
from app.services.rbac_auth_services import EnterpriseAuthorizationService
from app.api.deps import get_auth_enforcer, get_current_user
from app.utils.logger_config import logger
roles_router = APIRouter(tags=["Roles"], prefix="/api/roles")

@roles_router.post("/assign_role", response_model=bool)
async def assign_role_to_user(
    role_assignment: RoleAssignment,
    token_data: TokenData = Depends(get_current_user),
    enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer),
) -> Any:
    """
    TLDR: This endpoint assigns the specified role to the given user within the provided domain.
    Args:
        role_assignment (RoleAssignment): The role assignment details (user, role, domain).
        token_data (TokenData): The current user's token data (permission-checked).
        enforcer (EnterpriseAuthorizationService): The authorization enforcer dependency.

    Returns:
        bool: True if the role was successfully assigned.

    Raises:
        HTTPException: If the role assignment fails.
    """
    result = await enforcer.add_role_for_user(
        role_assignment.user, 
        role_assignment.role, 
        role_assignment.domain or "global"
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to assign role"
        )
    
    return result

@roles_router.delete("/remove_role", response_model=bool)
async def revoke_role_from_user(
    role_assignment: RoleAssignment,
    token_data: TokenData = Depends(get_current_user),
    enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer),
) -> Any:
    """
    TLDR: This endpoint revokes the specified role from the given user within the provided domain.
    Args:
        role_assignment (RoleAssignment): The role assignment details (user, role, domain).
        token_data (TokenData): The current user's token data (permission-checked).
        enforcer (EnterpriseAuthorizationService): The authorization enforcer dependency.

    Returns:
        bool: True if the role was successfully revoked.

    Raises:
        HTTPException: If the role revocation fails or the assignment does not exist.
    """
    result = await enforcer.remove_role_for_user(
        role_assignment.user, 
        role_assignment.role, 
        role_assignment.domain or "global"
    )
    
    if not result:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Failed to revoke role or role assignment not found"
        )
    
    return result

@roles_router.get("/roles/users/{user}", response_model=List[str])
async def get_user_roles(
    user: str,
    domain: str,
    token_data: TokenData = Depends(get_current_user),
    enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer),
) -> Any:
    """
    TLDR: Retrieve all roles assigned to a user in a specific domain.
    Args:
        user (str): The username or user identifier to fetch roles for.
        domain (str): The domain or tenant in which to look up the user's roles.
        token_data (TokenData): Authentication and authorization token data, injected by dependency.
        enforcer (EnterpriseAuthorizationService): Authorization service instance, injected by dependency.

    Returns:
        List[str]: A list of role names assigned to the specified user in the given domain. 
    Raises:
        HTTPException: If the user does not exist or access is denied
    """
    result = await enforcer.get_roles_for_user(user, domain)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No roles found for user '{user}' in domain '{domain}'"
        )
    return result

@roles_router.get("/roles/{role}/users", response_model=List[str])
async def get_role_users(
    role: str,
    domain: str,
    token_data: TokenData = Depends(get_current_user),
    enforcer: EnterpriseAuthorizationService = Depends(get_auth_enforcer),
) -> Any:
    """
    TLDR: Get all users assigned to a role in a domain.
    Args:
        role (str): The role name to fetch users for.
        domain (str): The domain or tenant in which to look up users for the role.
        token_data (TokenData): Authentication and authorization token data, injected by dependency.
        enforcer (EnterpriseAuthorizationService): Authorization service instance, injected by dependency.

    Returns:
        List[str]: A list of usernames or user IDs assigned to the specified role in the given domain.

    Raises:
        HTTPException: If the role does not exist or access is denied.
    """
    logger.info(f"Fetching users for role: {role} in domain: {domain}")
    result = await enforcer.get_users_for_role(role, domain)
    if not result:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No users found for role '{role}' in domain '{domain}'"
        )
    return result