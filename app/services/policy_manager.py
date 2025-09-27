from datetime import timezone, datetime
# from sqlalchemy.orm  import Session
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.models.policy_version import PolicyVersion


class DistributedPolicyManager:
    """
    TLDR: Manages policy versioning using PostgreSQL.
    This class provides methods to retrieve, set, increment, and check the version of
    authorization policies for a given domain(tenant). 
    Policy versioning is tracked in the 'policy_versions' table, where each domain(tenant) has a single version string and a timestamp
    of the last update.

    Attributes:
        db (AsyncSession): The asynchronous database session used for all operations.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def get_policy_version(self, domain: str) -> str:
        """
            TLDR:Retrieve the current policy version for a given domain.

            Args:
                domain (str): The domain identifier.

            Returns:
                str: The current policy version string for the tenant, or "0" if not found.
        """
        results = await self.db.execute(select(PolicyVersion).filter_by(tenant=domain))
        record = results.scalars().first()
        return record.version if record else "0"

    async def set_policy_version(self, domain, version: str = None) -> str:
        """
            TLDR:Set the policy version for a domain, updating or creating the record as needed.

            If the version is not provided, the current UTC timestamp (ISO format) is used.

            Args:
                domain (str): The domain identifier.
                version (str, optional): The version string to set. Defaults to current UTC timestamp.

            Returns:
                str: The version string that was set.
        """
        version = version or datetime.now(timezone.utc).isoformat()
        results = await self.db.execute(select(PolicyVersion).filter_by(tenant=domain))
        record = results.scalars().first()
        if record:
            record.version = version
            record.last_updated = datetime.now(timezone.utc)
        else:
            record = PolicyVersion(
                tenant=domain,
                version=version,
                last_updated=datetime.now(timezone.utc)
            )
            self.db.add(record)
        await self.db.commit()
        return version

    async def increment_policy_version(self, domain: str) -> str:
        """
            TLDR:Increment the policy version for a domain.

            If the current version is an integer, it is incremented by 1. If it is not an integer,
            the version is set to the current UTC timestamp (ISO format).

            Args:
                domain (str): The domain identifier.

            Returns:
                str: The new version string after incrementing.
        """
        current = await self.get_policy_version(domain)
        try:
            new_version = str(int(current) + 1)
        except ValueError:
            new_version = datetime.now(timezone.utc).isoformat()
        return self.set_policy_version(domain, new_version)

    async def is_policy_current(self, domain: str, version: str) -> bool:
        """
            TLDR:Check if the given version matches the current policy version for the domain.

            Args:
                domain (str): The domain identifier.
                version (str): The version string to compare.

            Returns:
                bool: True if the provided version matches the current version, False otherwise.
        """
        return await self.get_policy_version(domain) == version