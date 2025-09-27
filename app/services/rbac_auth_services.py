import os
from typing import List, Dict, Any, Optional
from casbin import Model
from casbin_sqlalchemy_adapter import Adapter as SQLAdapter
from casbin_sqlalchemy_adapter.adapter import Filter
# from app.services.enforcer import CachedEnforcer
from casbin import Enforcer
from app.utils.settings import settings
from app.services.metrics import ENFORCE_LATENCY, ENFORCE_COUNTER, POLICY_UPDATE_COUNTER
from app.database.models.users_models import User
from app.schemas.user_schemas import UserWithPassword, UserResponse
# from app.schemas.user_schemas import UserResponsewithActivity
from uuid import uuid4

# from app.models.policy import BatchOperation
# from app.services.audit_logger import AuditLogger
from app.services.policy_validator import PolicyValidator

# from app.services.policy_watcher import RedisPolicyWatcher
from app.services.policy_manager import DistributedPolicyManager
from app.utils.security import verify_password, get_password_hash, create_access_token
from app.utils.logger_config import logger
# from sqlalchemy.orm import 
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import time
from app.services.role_services import get_roles
import asyncio

class AuthService:    
    """
    TLDR: Service class for user authentication and management.This asynchronous service provides methods for 
    authenticating users, creating new users, generating JWT access tokens, and retrieving user information from the database.


    Key Features:
    - Authenticate users using email and password.
    - Create new users with hashed passwords and role assignment.
    - Generate JWT access tokens containing user identity and roles.
    - Retrieve users by full name or list users with flexible filters (name, activity, superuser).
    - Prevent duplicate user registration by email.

    Args:
        db (AsyncSession): The asynchronous SQLAlchemy database session for user operations.

    Methods:
        authenticate_user(email, password): Authenticate a user by email and password.
        create_user(user_create): Register a new user, ensuring unique email.
        create_access_token_for_user(user): Generate a JWT access token for a user.
        get_user_by_username(full_name): Retrieve a user by their full name.
        get_users(skip, limit, full_name, is_active, is_superuser): List users with optional filters.

    Example:
        auth_service = AuthService(db_session)
        user = await auth_service.authenticate_user("alice@example.com", "password123")
        if user:
            token = await auth_service.create_access_token_for_user(user)
    """
    def __init__(self, db: AsyncSession):
        self.db = db
    
    async def authenticate_user(self, email: str, password: str) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.email == email))
        user = result.scalars().first()
        if not user:
            return None
        if not await verify_password(password, user.password_hash):
            return None

        return user
    
    async def create_user(self, user_create: UserWithPassword) -> User:
        """Create a new user."""
        # Check if user already exists
        result = await self.db.execute(select(User).where(User.email == user_create.email))
        db_user = result.scalars().first()

        if db_user:
            if db_user.email == user_create.email:
                logger.error("Email already registered")
                raise ValueError("Email already registered")

        # Create new user
        logger.info(f"Type of role in UserRole: {type(user_create.role)}")
        
        password_hash = await get_password_hash(user_create.password)
        db_user = User(
            user_id=uuid4(),
            full_name=user_create.full_name,
            email=user_create.email,
            role=user_create.role,
            password_hash=password_hash,
        )

        self.db.add(db_user)
        await self.db.commit()
        await self.db.refresh(db_user)
        
        return db_user
    
    async def create_access_token_for_user(self, user: User) -> str:
        token_data = {
            "sub": user.email,
            "user_id": str(user.user_id),
            "role": await get_roles(self.db,user.email)
        }
        return await create_access_token(token_data)
    
    async def get_user_by_username(self, full_name: str) -> Optional[User]:
        """Retrieve a user by their full_name."""
        result = await self.db.execute(select(User).filter(User.full_name == full_name))
        return result.scalars().first()
    
    async def get_users(
        self, 
        skip: int = 0, 
        limit: int = 100, 
        full_name: Optional[str] = None, 
        is_active: Optional[bool] = None,
        is_superuser: Optional[bool] = None,
    ) -> List[UserResponse]:

        query = select(User)

        # Dynamically add filters
        conditions = []
        if full_name:
            conditions.append(User.full_name.ilike(f"%{full_name}%"))
        if is_active is not None:
            conditions.append(User.is_active == is_active)
        if is_superuser is not None:
            conditions.append(User.is_superuser == is_superuser)

        if conditions:
            from sqlalchemy import and_
            query = query.where(and_(*conditions))

        query = query.order_by(User.created_at.desc()).offset(skip).limit(limit)

        result = await self.db.execute(query)
        users = result.scalars().all()

        return [
            UserResponse(
                id=user.id,
                full_name=user.full_name,
                email=user.email,
                is_active=user.is_active,
                is_superuser=user.is_superuser,
                created_at=user.created_at,
                updated_at=user.updated_at
            )
            for user in users
        ]




class EnterpriseAuthorizationService:
    """
    TLDR: Main service class for the enterprise authorization system.This class manages authorization logic using Casbin, 
    including policy enforcement,role and policy management, policy validation, and distributed policy updates.

    Key Features:
    - Initializes Casbin model, enforcer, watcher, policy manager, and validators.
    - Loads and manages authorization policies, with optional auto-loading and filtering by tenant.
    - Provides asynchronous methods to enforce access control decisions.
    - Supports adding, removing, and validating policies.
    - Manages roles for users within domains, including assignment and removal.
    - Retrieves roles, users, and permissions for audit and introspection.
    - Supports batch enforcement requests.
    - Integrates with Redis for distributed policy updates if enabled.

    Args:
        db (AsyncSession): Asynchronous database session for policy storage.
        config (Dict[str, Any], optional): Configuration dictionary for service options.
            Supported keys include:
                - 'enable_watcher' (bool): Enable Redis watcher for distributed updates.
                - 'model_path' (str): Path to the Casbin model file.
                - 'redis_url' (str): Redis connection URL for watcher.
                - 'schema_path' (str): Path to policy schema for validation.
                - 'auto_load_policies' (bool): Automatically load policies on startup.

    Example:
        service = EnterpriseAuthorizationService(db_session, config)
        await service.add_policy("alice", "tenant1", "data1", "read")
        allowed = await service.enforce("alice", "tenant1", "data1", "read")
    """

    def __init__(self, db: AsyncSession, config: Dict[str, Any] = None):
        self.db = db
        self.config = config or {"enable_watcher": False}

        self._init_model()
        self._init_enforcer()
        self._init_watcher()
        # self._init_audit_logger()
        self._init_policy_manager()
        self._init_validators()
        

        if self.config.get('auto_load_policies', True):
            asyncio.create_task(self.load_policies())

        logger.info("Enterprise Authorization Service initialized successfully")


    def _init_model(self):
        model_path = self.config.get('model_path', settings.CASBIN_MODEL_PATH)
        if not os.path.exists(model_path):
            logger.warning(f"Model file not found at {model_path}, using default model")
            self.model = self._get_default_model()
        else:
            self.model = Model()
            self.model.load_model(model_path)
            logger.info(f"Loaded Casbin model from {model_path}")


    def _get_default_model(self) -> Model:
        model = Model()
        model.add_def("r", "r", "sub, dom, obj, act")
        model.add_def("p", "p", "sub, dom, obj, act, eft")
        model.add_def("g", "g", "_, _, _")
        model.add_def("e", "e", "some(where (p.eft == allow))")
        model.add_def(
            "m",
            "m",
            "g(r.sub, p.sub, r.dom) && r.dom == p.dom && (r.obj == p.obj || p.obj == '*') && (r.act == p.act || p.act == '*')",
        )
        return model

    def _init_enforcer(self):
        adapter = SQLAdapter(settings.DB_URL)
        self.enforcer = Enforcer(self.model, adapter)
        self.enforcer.enable_auto_save(True)
        logger.info("Casbin enforcer initialized with caching adapter")

    def _init_watcher(self):
        try:
            if not self.config.get("enable_watcher", True):
                logger.info("Casbin watcher is disabled in configuration")
                return

            from casbin_redis_watcher import Watcher
            redis_url = self.config.get("redis_url", "redis://localhost:6379")
            watcher = Watcher(redis_url)
            self.enforcer.set_watcher(watcher)
            logger.info("Casbin Redis watcher initialized successfully")

        except Exception as e:
            logger.warning(f"Redis watcher initialization failed, continuing without it: {e}")

    def _init_policy_manager(self):
        self.policy_manager = DistributedPolicyManager(self.db)
        logger.info("Distributed policy manager initialized")


    def _init_validators(self):
        schema_path = self.config.get("schema_path", "config/policy_schema.json")
        self.policy_validator = PolicyValidator(schema_path)
        logger.info("Policy validator initialized")

    async def load_policies(self, tenant: str = None):
        """
        Loads policies from the database.

        Args:
            tenant: Optional tenant/domain to load policies for
        """
        logger.info(f"Loading policies{' for tenant ' + tenant if tenant else ''}")
        try:
            self.enforcer.clear_policy()
            if tenant:
                filter = Filter()
                filter.p_type = ["p", "g"]
                filter.v1 = [tenant]
                await asyncio.to_thread(self.enforcer.get_adapter().load_filtered_policy, filter)
            else:
                await asyncio.to_thread(self.enforcer.load_policy)
            self.enforcer.build_role_links()
            logger.info(
                f"Successfully loaded policies{' for tenant ' + tenant if tenant else ''}"
            )
        except Exception as e:
            logger.error(f"Failed to load policies: {e}")

    async def enforce(self, subject: str, domain: str, object: str, action: str, context: Dict[str, Any] = None) -> bool:
        """
            Checks if a subject has permission to perform an action on an object in a domain.

            Args:
                subject: The user or role
                domain: The tenant or domain
                object: The resource
                action: The operation
                context: Additional context attributes for ABAC

            Returns:
                bool: Whether access is allowed
        """
        
        start_time = time.time()
        request = [subject, domain, object, action]
        logger.info(f"Enforce request received: {request}")
        try:
            result = await asyncio.to_thread(self.enforcer.enforce, *request)
            logger.info(f"Enforcement result: {result}")
            latency = time.time() - start_time
            ENFORCE_LATENCY.labels(domain, str(result)).observe(latency)
            ENFORCE_COUNTER.labels(domain, str(result)).inc()
            return result
        except Exception as e:
            logger.info(f"Enforcement error: {e}")
            return False

    async def add_policy(self, subject: str, domain: str, object: str, action: str, effect: str = "allow") -> bool:
        """
        Adds a policy to the system.

        Args:
            subject: The user or role
            domain: The tenant or domain
            object: The resource
            action: The operation
            effect: Allow or deny

        Returns:
            bool: Whether the policy was added successfully
        """
        policy = [subject, domain, object, action, effect]
        valid, message = self.policy_validator.validate_policy(policy)
        if not valid:
            logger.warning(f"Invalid policy: {message}")
            return False

        result = await asyncio.to_thread(self.enforcer.add_policy, *policy)
        if result:
            await self.policy_manager.increment_policy_version(domain)
            POLICY_UPDATE_COUNTER.labels(domain, "add").inc()
            logger.info(f"Policy added: {policy}")
        return result

    async def remove_policy(self, subject: str, domain: str, object: str, action: str, effect: str = "allow") -> bool:
        """
            Removes a policy from the system.

            Args:
                subject: The user or role
                domain: The tenant or domain
                object: The resource
                action: The operation
                effect: Allow or deny

            Returns:
                bool: Whether the policy was removed successfully
        """
        policy = [subject, domain, object, action, effect]
        result = await asyncio.to_thread(self.enforcer.remove_policy, *policy)
        if result:
            await self.policy_manager.increment_policy_version(domain)
            POLICY_UPDATE_COUNTER.labels(domain, "remove").inc()
            logger.info(f"Policy removed: {policy}")
        return result

    async def has_policy(self, *args) -> bool:
        return await asyncio.to_thread(self.enforcer.has_policy, *args)

    async def has_role_for_user(self, user: str, role: str, domain: str = None) -> bool:
        if domain:
            roles = await asyncio.to_thread(self.enforcer.get_roles_for_user_in_domain, user, domain)
        else:
            roles = await asyncio.to_thread(self.enforcer.get_roles_for_user, user)
        return role in roles

    async def add_role_for_user(self, user: str, role: str, domain: str) -> bool:
        """
            Assigns a role to a user.

            Args:
                user: The user
                role: The role
                domain: The tenant or domain

            Returns:
                bool: Whether the role was assigned successfully
        """
        result = await asyncio.to_thread(self.enforcer.add_grouping_policy, user, role, domain)
        if result:
            await self.policy_manager.increment_policy_version(domain)
            POLICY_UPDATE_COUNTER.labels(domain, "add_role").inc()
            logger.info(f"Role assigned: {user} -> {role} in {domain}")
        return result

    async def remove_role_for_user(self, user: str, role: str, domain: str) -> bool:
        """
        Removes a role from a user.

        Args:
            user: The user
            role: The role
            domain: The tenant or domain

        Returns:
            bool: Whether the role was removed successfully
        """
        result = await asyncio.to_thread(self.enforcer.remove_grouping_policy, user, role, domain)
        if result:
            await self.policy_manager.increment_policy_version(domain)
            POLICY_UPDATE_COUNTER.labels(domain, "remove_role").inc()
            logger.info(f"Role removed: {user} -> {role} in {domain}")
        return result

    async def get_roles_for_user(self, user: str, domain: str) -> List[str]:
        """
            Gets all roles assigned to a user.

            Args:
                user: The user
                domain: The tenant or domain

            Returns:
                List[str]: List of roles
        """
        return await asyncio.to_thread(self.enforcer.get_roles_for_user_in_domain, user, domain)

    async def get_users_for_role(self, role: str, domain: str) -> List[str]:
        """
            Gets all users assigned to a role.

            Args:
                role: The role
                domain: The tenant or domain

            Returns:
                List[str]: List of users
        """
        return await asyncio.to_thread(self.enforcer.get_users_for_role_in_domain, role, domain)

    async def get_implicit_permissions_for_user(self, user: str, domain: str) -> List[List[str]]:
        return await asyncio.to_thread(self.enforcer.get_implicit_permissions_for_user_in_domain, user, domain)

    async def get_implicit_roles_for_user(self, user: str, domain: str) -> List[str]:
        """
        Gets all roles granted to a user including through role inheritance.

        Args:
            user: The user
            domain: The tenant or domain

        Returns:
            List[str]: List of roles
        """
        return await asyncio.to_thread(self.enforcer.get_roles_for_user_in_domain, user, domain)

    async def batch_enforce(self, requests: List[List[str]]) -> List[bool]:
        """
            Performs multiple enforcement checks at once.

            Args:
                requests: List of enforcement requests

            Returns:
                List[bool]: List of enforcement results
        """
        results = []
        for request in requests:
            if len(request) >= 4:
                subject, domain, object, action = request[:4]
                context = request[4] if len(request) > 4 else None
                result = await self.enforce(subject, domain, object, action, context)
            else:
                result = False
                logger.warning(f"Invalid enforcement request: {request}")
            results.append(result)
        return results

