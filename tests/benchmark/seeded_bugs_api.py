"""
BENCHMARK TEST FILE #2 - API/Web Application Bugs
=================================================
This file simulates a web API with common security and logic bugs.
Contains 10 additional seeded bugs.

DO NOT FIX THESE BUGS - They are intentional for benchmarking purposes.
=================================================
"""

from typing import Optional, Dict, List, Any
import re
import pickle
import subprocess


class UserService:
    """Service for managing users."""
    
    def __init__(self):
        self.users: Dict[str, Dict] = {}
        self.session_tokens: Dict[str, str] = {}
    
    # =========================================================================
    # BUG #16: Command Injection (SECURITY - CRITICAL)
    # User input passed directly to shell command
    # =========================================================================
    def ping_server(self, hostname: str) -> str:
        """Ping a server to check if it's online."""
        # BUG: Command injection - hostname not sanitized
        result = subprocess.run(
            f"ping -c 1 {hostname}",
            shell=True,  # BUG: shell=True with user input
            capture_output=True,
            text=True
        )
        return result.stdout
    
    # =========================================================================
    # BUG #17: Insecure Deserialization (SECURITY - CRITICAL)
    # Using pickle to deserialize untrusted data
    # =========================================================================
    def load_user_preferences(self, data: bytes) -> dict:
        """Load user preferences from serialized data."""
        # BUG: Pickle deserialization of untrusted data - RCE vulnerability
        return pickle.loads(data)
    
    # =========================================================================
    # BUG #18: Broken Authentication (SECURITY - HIGH)
    # Weak session token generation
    # =========================================================================
    def create_session(self, user_id: str) -> str:
        """Create a session token for a user."""
        # BUG: Predictable session token based on user_id
        import time
        token = f"{user_id}_{int(time.time())}"  # Easily guessable!
        self.session_tokens[token] = user_id
        return token
    
    # =========================================================================
    # BUG #19: Missing Authorization Check (SECURITY - HIGH)
    # Any user can delete any other user
    # =========================================================================
    def delete_user(self, target_user_id: str, requesting_user_id: str) -> bool:
        """Delete a user account."""
        # BUG: No authorization check - any user can delete any user
        if target_user_id in self.users:
            del self.users[target_user_id]
            return True
        return False
    
    # =========================================================================
    # BUG #20: ReDoS Vulnerability (SECURITY - MEDIUM)
    # Regex pattern vulnerable to catastrophic backtracking
    # =========================================================================
    def validate_input(self, text: str) -> bool:
        """Validate user input format."""
        # BUG: ReDoS - evil regex with nested quantifiers
        pattern = r"^(a+)+$"
        return bool(re.match(pattern, text))


class PaymentProcessor:
    """Service for processing payments."""
    
    def __init__(self):
        self.transactions: List[Dict] = []
    
    # =========================================================================
    # BUG #21: Floating Point Comparison (LOGIC - MEDIUM)
    # Comparing floats for equality
    # =========================================================================
    def verify_payment(self, expected: float, received: float) -> bool:
        """Verify that the received payment matches expected amount."""
        # BUG: Floating point comparison - 0.1 + 0.2 != 0.3
        return expected == received
    
    # =========================================================================
    # BUG #22: TOCTOU Race Condition (CONCURRENCY - HIGH)
    # Time-of-check to time-of-use vulnerability
    # =========================================================================
    def process_withdrawal(self, account_id: str, amount: float, balance: Dict[str, float]) -> bool:
        """Process a withdrawal if sufficient balance exists."""
        # BUG: TOCTOU - balance can change between check and update
        if balance.get(account_id, 0) >= amount:
            # Gap here where another thread could modify balance
            balance[account_id] -= amount
            return True
        return False
    
    # =========================================================================
    # BUG #23: Integer Overflow (LOGIC - MEDIUM)
    # Not handling large numbers properly
    # =========================================================================
    def calculate_total_with_fee(self, amount: int, fee_percent: int) -> int:
        """Calculate total amount including fee."""
        # BUG: Potential overflow in multiplication before division
        # In Python this won't overflow but the logic is still wrong for cents
        fee = amount * fee_percent / 100
        return int(amount + fee)  # Precision loss!


class DataValidator:
    """Utility class for data validation."""
    
    # =========================================================================
    # BUG #24: Incorrect Regex for Email (LOGIC - LOW)
    # Overly permissive email regex
    # =========================================================================
    def is_valid_email(self, email: str) -> bool:
        """Check if email is valid."""
        # BUG: Overly simple regex - accepts invalid emails like "a@b"
        pattern = r".+@.+"
        return bool(re.match(pattern, email))
    
    # =========================================================================
    # BUG #25: Type Confusion (LOGIC - MEDIUM)
    # Not validating input type before operations
    # =========================================================================
    def safe_divide(self, a: Any, b: Any) -> float:
        """Safely divide two numbers."""
        # BUG: No type validation - will fail silently with strings
        if b == 0:
            return 0.0
        return a / b  # Will raise TypeError if a or b is not a number


# =============================================================================
# Additional standalone functions with bugs
# =============================================================================

# =========================================================================
# BUG #26: Timing Attack Vulnerability (SECURITY - MEDIUM)
# String comparison short-circuits on mismatch
# =========================================================================
def verify_api_key(provided_key: str, stored_key: str) -> bool:
    """Verify an API key."""
    # BUG: Timing attack - comparison short-circuits
    return provided_key == stored_key  # Should use hmac.compare_digest


# =========================================================================
# BUG #27: Improper Error Message (SECURITY - LOW)
# Leaking sensitive information in error message
# =========================================================================
def authenticate_user(username: str, password: str, users_db: Dict) -> Dict:
    """Authenticate a user and return their profile."""
    user = users_db.get(username)
    
    if not user:
        # BUG: Information disclosure - reveals if username exists
        raise ValueError(f"User '{username}' does not exist")
    
    if user["password"] != password:
        # BUG: Should not differentiate between bad user and bad password
        raise ValueError("Incorrect password")
    
    return user


# =============================================================================
# GROUND TRUTH - Bug Summary for Evaluation
# =============================================================================
SEEDED_BUGS_FILE2 = {
    "security": [
        {"id": 16, "type": "Command Injection", "severity": "CRITICAL", "line": 29},
        {"id": 17, "type": "Insecure Deserialization", "severity": "CRITICAL", "line": 41},
        {"id": 18, "type": "Weak Session Token", "severity": "HIGH", "line": 51},
        {"id": 19, "type": "Missing Authorization", "severity": "HIGH", "line": 62},
        {"id": 20, "type": "ReDoS", "severity": "MEDIUM", "line": 74},
        {"id": 26, "type": "Timing Attack", "severity": "MEDIUM", "line": 126},
        {"id": 27, "type": "Information Disclosure", "severity": "LOW", "line": 137},
    ],
    "logic": [
        {"id": 21, "type": "Float Comparison", "severity": "MEDIUM", "line": 88},
        {"id": 23, "type": "Precision Loss", "severity": "MEDIUM", "line": 105},
        {"id": 24, "type": "Weak Regex", "severity": "LOW", "line": 116},
        {"id": 25, "type": "Type Confusion", "severity": "MEDIUM", "line": 123},
    ],
    "concurrency": [
        {"id": 22, "type": "TOCTOU Race", "severity": "HIGH", "line": 96},
    ],
}

TOTAL_BUGS_FILE2 = 12
