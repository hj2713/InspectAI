"""
Sample Python code with various issues for testing the multi-agent review system.
This file intentionally contains naming, quality, bug, and security issues.
"""

import os
import pickle

# Bad naming - should be UPPER_CASE for constant
apiKey = "sk-1234567890abcdef"  # Security issue: hardcoded secret

def calculate(x,y):  # Missing type hints, poor name
    """Calculate something"""  # Vague docstring
    result=x/y  # Edge case: division by zero possible, spacing issues
    return result

class userManager:  # Bad naming: should be PascalCase
    def __init__(self,db):  # Missing spaces after commas
        self.db=db  # No space around =
        
    def get_user(self,id):  # Missing type hints
        # SQL injection vulnerability
        query = f"SELECT * FROM users WHERE id = {id}"
        return self.db.execute(query)
    
    def load_data(self,filename):
        # Security: unsafe deserialization
        with open(filename,'rb') as f:
            data=pickle.load(f)
        return data

def process_list(items):
    # Logic error: off-by-one
    for i in range(1, len(items)):
        print(items[i])  # Skips first item
    
    # Code duplication
    total = 0
    for item in items:
        total += item
    
    sum_val = 0
    for item in items:
        sum_val += item  # Duplicate logic
    
    return total,sum_val

# Runtime issue: file not closed properly
def read_file(path):
    f = open(path)  # Should use 'with' statement
    content = f.read()
    return content  # File never closed

# Type error
def concat(a, b):
    return a + b  # Could fail if types don't match

result = concat("Hello", 123)  # Type mismatch

# Missing edge case handling
def get_first(lst):
    return lst[0]  # No check for empty list

print(get_first([]))  # This will crash
