
import os
import json
from typing import Tuple, List

class PolicyValidator:
    def __init__(self, schema_path: str = None):
        self.schema = {}
        if schema_path and os.path.exists(schema_path):
            with open(schema_path, 'r') as f:
                self.schema = json.load(f)
    
    def validate_policy(self, policy: List[str]) -> Tuple[bool, str]:
        """
        Validates a policy against the schema.
        
        Args:
            policy: A policy entry as a list of strings
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if len(policy) < 4:
            return False, "Policy must have at least 4 elements"
        
        # Subject validation
        if policy[0].startswith('role:') and not self.validate_role_name(policy[0][5:]):
            return False, f"Invalid role name: {policy[0]}"
            
        # Domain validation
        if policy[1] != '*' and not self.validate_domain(policy[1]):
            return False, f"Invalid domain: {policy[1]}"
        
        # Object validation
        if policy[2] != '*' and not self.validate_object(policy[2]):
            return False, f"Invalid object: {policy[2]}"
        
        # Action validation
        valid_actions = self.schema.get('actions', ['read', 'write', 'create', 'update', 'delete'])
        if not policy[3] or not isinstance(policy[3], str):
            return False, "Action must be a non-empty string"
        
        return True, ""
    
    def validate_role_name(self, role_name: str) -> bool:
        """Validates a role name against naming conventions."""
        return all(c.isalnum() or c in ['_', '-'] for c in role_name)
    
    def validate_domain(self, domain: str) -> bool:
        """Validates a domain identifier."""
        parts = domain.split(':')
        if len(parts) != 2:
            return False
        return all(c.isalnum() or c in ['_', '-'] for c in parts[1])
    
    def validate_object(self, obj: str) -> bool:
        """Validates an object identifier."""
        if '*' in obj and obj != '*':
            # Check for valid glob pattern
            parts = obj.split(':')
            if len(parts) != 2:
                return False
            return True
        return True