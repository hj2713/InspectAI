"""
BENCHMARK TEST FILE - Contains intentionally seeded bugs for testing InspectAI
================================================================================
This file contains 15 seeded bugs across different categories:
- Security vulnerabilities (SQL injection, hardcoded secrets, XSS)
- Logic errors (off-by-one, wrong operator, missing return)
- Null/None handling issues
- Resource leaks
- Race conditions
- Type errors

DO NOT FIX THESE BUGS - They are intentional for benchmarking purposes.
================================================================================
"""

import os
import sqlite3
import hashlib
import threading
from typing import List, Optional, Dict, Any


# =============================================================================
# BUG #1: SQL Injection Vulnerability (SECURITY - HIGH)
# The user_id is directly interpolated into the SQL query
# =============================================================================
def get_user_by_id(user_id: str) -> dict:
    """Fetch a user from the database by their ID."""
    conn = sqlite3.connect("users.db")
    cursor = conn.cursor()
    
    # BUG: SQL Injection - user_id is not parameterized
    query = f"SELECT * FROM users WHERE id = '{user_id}'"
    cursor.execute(query)
    
    result = cursor.fetchone()
    conn.close()
    return {"id": result[0], "name": result[1]} if result else None


# =============================================================================
# BUG #2: Hardcoded Secret/API Key (SECURITY - CRITICAL)
# API keys should never be hardcoded in source code
# =============================================================================
API_KEY = "sk-live-abc123def456ghi789jkl012mno345pqr678"
DATABASE_PASSWORD = "super_secret_password_123!"

def make_api_request(endpoint: str) -> dict:
    """Make an authenticated API request."""
    headers = {"Authorization": f"Bearer {API_KEY}"}
    # Simulated request
    return {"status": "ok", "endpoint": endpoint}


# =============================================================================
# BUG #3: Off-by-One Error (LOGIC - MEDIUM)
# Loop should use range(len(items)) or enumerate, not len(items) + 1
# =============================================================================
def process_items(items: List[str]) -> List[str]:
    """Process each item in the list."""
    results = []
    
    # BUG: Off-by-one - will cause IndexError on last iteration
    for i in range(len(items) + 1):
        results.append(items[i].upper())
    
    return results


# =============================================================================
# BUG #4: Missing Null Check (LOGIC - MEDIUM)
# Accessing attributes without checking if object is None
# =============================================================================
def get_user_email(user: Optional[Dict]) -> str:
    """Get the user's email address."""
    # BUG: No null check - will raise KeyError/TypeError if user is None
    return user["email"].lower()


# =============================================================================
# BUG #5: Resource Leak - File Not Closed (RESOURCE - MEDIUM)
# File handle is never closed, leading to resource leak
# =============================================================================
def read_config_file(path: str) -> str:
    """Read configuration from a file."""
    # BUG: File is never closed - resource leak
    f = open(path, "r")
    content = f.read()
    # Missing: f.close() or use 'with' statement
    return content


# =============================================================================
# BUG #6: Wrong Comparison Operator (LOGIC - HIGH)
# Using = instead of == in comparison (though Python will error, 
# using 'is' instead of '==' for value comparison is the realistic bug)
# =============================================================================
def check_status(status: str) -> bool:
    """Check if the status indicates success."""
    # BUG: Using 'is' instead of '==' for string comparison
    # This may work for small strings due to interning but is incorrect
    if status is "success":
        return True
    elif status is "pending":
        return False
    return False


# =============================================================================
# BUG #7: Integer Division Truncation (LOGIC - LOW)
# In Python 3 this is fine, but the logic error is wrong formula
# =============================================================================
def calculate_average(numbers: List[int]) -> float:
    """Calculate the average of a list of numbers."""
    if not numbers:
        return 0
    
    # BUG: Using len(numbers) - 1 instead of len(numbers)
    total = sum(numbers)
    return total / (len(numbers) - 1)  # Wrong divisor!


# =============================================================================
# BUG #8: Race Condition (CONCURRENCY - HIGH)
# Shared counter without proper synchronization
# =============================================================================
counter = 0

def increment_counter():
    """Increment the global counter (not thread-safe)."""
    global counter
    # BUG: Race condition - read-modify-write is not atomic
    temp = counter
    temp += 1
    counter = temp


def run_concurrent_increments():
    """Run multiple increments concurrently."""
    threads = []
    for _ in range(100):
        t = threading.Thread(target=increment_counter)
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    return counter


# =============================================================================
# BUG #9: XSS Vulnerability (SECURITY - HIGH)
# User input directly embedded in HTML without escaping
# =============================================================================
def render_user_profile(username: str, bio: str) -> str:
    """Render a user profile as HTML."""
    # BUG: XSS vulnerability - user input not escaped
    html = f"""
    <div class="profile">
        <h1>Welcome, {username}!</h1>
        <p class="bio">{bio}</p>
    </div>
    """
    return html


# =============================================================================
# BUG #10: Weak Password Hashing (SECURITY - CRITICAL)
# Using MD5 for password hashing is insecure
# =============================================================================
def hash_password(password: str) -> str:
    """Hash a password for storage."""
    # BUG: MD5 is cryptographically broken, should use bcrypt/argon2
    return hashlib.md5(password.encode()).hexdigest()


def verify_password(password: str, hash_value: str) -> bool:
    """Verify a password against its hash."""
    return hash_password(password) == hash_value


# =============================================================================
# BUG #11: Missing Return Statement (LOGIC - MEDIUM)
# Function doesn't return anything in success case
# =============================================================================
def validate_email(email: str) -> bool:
    """Validate an email address format."""
    if "@" not in email:
        return False
    
    if "." not in email.split("@")[1]:
        return False
    
    # BUG: Missing return True at the end
    # Function implicitly returns None when email is valid


# =============================================================================
# BUG #12: Mutable Default Argument (LOGIC - MEDIUM)
# Using mutable default argument causes unexpected behavior
# =============================================================================
def add_item_to_list(item: str, item_list: List[str] = []) -> List[str]:
    """Add an item to a list and return it."""
    # BUG: Mutable default argument - list persists across calls
    item_list.append(item)
    return item_list


# =============================================================================
# BUG #13: Unhandled Exception (ERROR HANDLING - MEDIUM)
# No exception handling for JSON parsing
# =============================================================================
import json

def parse_user_input(data: str) -> dict:
    """Parse JSON user input."""
    # BUG: No try-except - will crash on invalid JSON
    parsed = json.loads(data)
    return parsed


# =============================================================================
# BUG #14: Path Traversal Vulnerability (SECURITY - HIGH)
# User input used directly in file path without validation
# =============================================================================
def read_user_file(filename: str) -> str:
    """Read a file from the user uploads directory."""
    # BUG: Path traversal - user can access any file with ../
    base_path = "/var/uploads/"
    file_path = base_path + filename  # No sanitization!
    
    with open(file_path, "r") as f:
        return f.read()


# =============================================================================
# BUG #15: Infinite Loop Risk (LOGIC - HIGH)
# Loop condition may never become false
# =============================================================================
def find_target(numbers: List[int], target: int) -> int:
    """Find the index of target in a sorted list using binary search."""
    left = 0
    right = len(numbers) - 1
    
    # BUG: Missing update to left/right in some cases causes infinite loop
    while left <= right:
        mid = (left + right) // 2
        
        if numbers[mid] == target:
            return mid
        elif numbers[mid] < target:
            left = mid  # BUG: Should be mid + 1
        else:
            right = mid  # BUG: Should be mid - 1
    
    return -1


# =============================================================================
# GROUND TRUTH - Bug Summary for Evaluation
# =============================================================================
SEEDED_BUGS = {
    "security": [
        {"id": 1, "type": "SQL Injection", "severity": "HIGH", "line": 31},
        {"id": 2, "type": "Hardcoded Secret", "severity": "CRITICAL", "line": 41},
        {"id": 9, "type": "XSS", "severity": "HIGH", "line": 118},
        {"id": 10, "type": "Weak Crypto (MD5)", "severity": "CRITICAL", "line": 131},
        {"id": 14, "type": "Path Traversal", "severity": "HIGH", "line": 168},
    ],
    "logic": [
        {"id": 3, "type": "Off-by-One", "severity": "MEDIUM", "line": 56},
        {"id": 4, "type": "Missing Null Check", "severity": "MEDIUM", "line": 66},
        {"id": 6, "type": "Wrong Operator (is vs ==)", "severity": "HIGH", "line": 86},
        {"id": 7, "type": "Wrong Formula", "severity": "LOW", "line": 99},
        {"id": 11, "type": "Missing Return", "severity": "MEDIUM", "line": 141},
        {"id": 12, "type": "Mutable Default Arg", "severity": "MEDIUM", "line": 152},
        {"id": 15, "type": "Infinite Loop", "severity": "HIGH", "line": 181},
    ],
    "resource": [
        {"id": 5, "type": "Resource Leak", "severity": "MEDIUM", "line": 76},
    ],
    "concurrency": [
        {"id": 8, "type": "Race Condition", "severity": "HIGH", "line": 107},
    ],
    "error_handling": [
        {"id": 13, "type": "Unhandled Exception", "severity": "MEDIUM", "line": 160},
    ],
}

TOTAL_BUGS = 15
