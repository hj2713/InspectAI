"""Few-shot example selector for code reviews.

Selects relevant examples based on language and task type
to include in prompts for better LLM output quality.
"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path


class ExampleSelector:
    """Selects relevant few-shot examples for prompts."""
    
    def __init__(self, examples_dir: Optional[str] = None):
        """Initialize the example selector.
        
        Args:
            examples_dir: Path to directory containing example JSON files.
                         Defaults to ./examples relative to this file.
        """
        if examples_dir is None:
            examples_dir = Path(__file__).parent / "examples"
        self.examples_dir = Path(examples_dir)
        self._examples_cache: Dict[str, List[Dict]] = {}
        self._load_examples()
    
    def _load_examples(self) -> None:
        """Load all examples from JSON files."""
        if not self.examples_dir.exists():
            return
        
        for json_file in self.examples_dir.glob("*.json"):
            try:
                with open(json_file, 'r') as f:
                    data = json.load(f)
                    key = json_file.stem  # filename without extension
                    self._examples_cache[key] = data.get("examples", [])
            except (json.JSONDecodeError, IOError) as e:
                print(f"Warning: Failed to load examples from {json_file}: {e}")
    
    def get_examples(
        self,
        language: str,
        task_type: str,
        max_examples: int = 2
    ) -> List[Dict[str, Any]]:
        """Get relevant examples for a language and task type.
        
        Args:
            language: Programming language (python, javascript, etc.)
            task_type: Type of task (code_review, bug_detection, security_audit)
            max_examples: Maximum number of examples to return
            
        Returns:
            List of example dictionaries
        """
        # Try language-specific examples first
        key = f"{language.lower()}_{task_type}"
        examples = self._examples_cache.get(key, [])
        
        # Fall back to general examples for the task type
        if not examples:
            key = f"general_{task_type}"
            examples = self._examples_cache.get(key, [])
        
        # Fall back to any examples for the language
        if not examples:
            key = language.lower()
            examples = self._examples_cache.get(key, [])
        
        # Fall back to built-in examples
        if not examples:
            examples = self._get_builtin_examples(language, task_type)
        
        return examples[:max_examples]
    
    def _get_builtin_examples(
        self, 
        language: str, 
        task_type: str
    ) -> List[Dict[str, Any]]:
        """Get built-in examples when no JSON files are available."""
        
        # Built-in examples for common cases
        builtin = {
            ("python", "code_review"): [
                {
                    "language": "python",
                    "input_code": """def get_user(user_id):
    query = f"SELECT * FROM users WHERE id = {user_id}"
    return db.execute(query)""",
                    "expected_output": {
                        "line": 2,
                        "severity": "critical",
                        "category": "security",
                        "description": "SQL injection vulnerability. User input is directly interpolated into SQL query.",
                        "fix_suggestion": "Use parameterized queries: db.execute('SELECT * FROM users WHERE id = ?', (user_id,))",
                        "confidence": 0.95
                    }
                },
                {
                    "language": "python",
                    "input_code": """def process_items(items=[]):
    items.append("processed")
    return items""",
                    "expected_output": {
                        "line": 1,
                        "severity": "high",
                        "category": "bug",
                        "description": "Mutable default argument. The list will be shared across all calls without arguments.",
                        "fix_suggestion": "Use None as default and create list inside function: def process_items(items=None): items = items or []",
                        "confidence": 0.9
                    }
                }
            ],
            ("python", "bug_detection"): [
                {
                    "language": "python",
                    "input_code": """def divide(a, b):
    return a / b

result = divide(10, 0)""",
                    "expected_output": {
                        "line": 2,
                        "severity": "high",
                        "category": "bug",
                        "description": "Division by zero not handled. Will raise ZeroDivisionError when b=0.",
                        "fix_suggestion": "Add check: if b == 0: raise ValueError('Cannot divide by zero') or return a default value",
                        "confidence": 0.85
                    }
                }
            ],
            ("python", "security_audit"): [
                {
                    "language": "python",
                    "input_code": """import pickle

def load_data(user_file):
    with open(user_file, 'rb') as f:
        return pickle.load(f)""",
                    "expected_output": {
                        "line": 5,
                        "severity": "critical",
                        "category": "security",
                        "description": "Unsafe deserialization. pickle.load on untrusted data can execute arbitrary code.",
                        "fix_suggestion": "Use safe alternatives like json.load() or validate file source. Never unpickle untrusted data.",
                        "confidence": 0.95
                    }
                }
            ],
            ("javascript", "code_review"): [
                {
                    "language": "javascript",
                    "input_code": """function getUserById(id) {
    if (id == null) {
        return null;
    }
    return users.find(u => u.id == id);
}""",
                    "expected_output": {
                        "line": 5,
                        "severity": "medium",
                        "category": "bug",
                        "description": "Using == instead of === for comparison. This allows type coercion which can cause unexpected matches.",
                        "fix_suggestion": "Use strict equality: users.find(u => u.id === id)",
                        "confidence": 0.85
                    }
                }
            ],
            ("javascript", "security_audit"): [
                {
                    "language": "javascript",
                    "input_code": """function displayMessage(userInput) {
    document.getElementById('message').innerHTML = userInput;
}""",
                    "expected_output": {
                        "line": 2,
                        "severity": "critical",
                        "category": "security",
                        "description": "XSS vulnerability. User input directly assigned to innerHTML can execute malicious scripts.",
                        "fix_suggestion": "Use textContent instead: document.getElementById('message').textContent = userInput",
                        "confidence": 0.95
                    }
                }
            ],
            ("typescript", "code_review"): [
                {
                    "language": "typescript",
                    "input_code": """function processUser(user: any) {
    console.log(user.name.toUpperCase());
    return user.id;
}""",
                    "expected_output": {
                        "line": 1,
                        "severity": "medium",
                        "category": "style",
                        "description": "Using 'any' type defeats TypeScript's type safety. User properties are not validated.",
                        "fix_suggestion": "Define a proper interface: interface User { id: number; name: string; } and use it as the parameter type",
                        "confidence": 0.8
                    }
                }
            ],
            ("java", "bug_detection"): [
                {
                    "language": "java",
                    "input_code": """public String getUserName(User user) {
    return user.getName().toUpperCase();
}""",
                    "expected_output": {
                        "line": 2,
                        "severity": "high",
                        "category": "bug",
                        "description": "Potential NullPointerException. Neither user nor getName() result is null-checked.",
                        "fix_suggestion": "Add null checks: if (user != null && user.getName() != null) { return user.getName().toUpperCase(); } return null;",
                        "confidence": 0.85
                    }
                }
            ],
            ("go", "code_review"): [
                {
                    "language": "go",
                    "input_code": """func readFile(path string) []byte {
    data, _ := ioutil.ReadFile(path)
    return data
}""",
                    "expected_output": {
                        "line": 2,
                        "severity": "high",
                        "category": "bug",
                        "description": "Error ignored. File read errors are silently discarded, function may return nil.",
                        "fix_suggestion": "Handle the error: data, err := ioutil.ReadFile(path); if err != nil { return nil, err }",
                        "confidence": 0.9
                    }
                }
            ]
        }
        
        # Try exact match
        key = (language.lower(), task_type)
        if key in builtin:
            return builtin[key]
        
        # Try just the task type with python (most common)
        fallback_key = ("python", task_type)
        if fallback_key in builtin:
            return builtin[fallback_key]
        
        # Return generic python code review example
        return builtin.get(("python", "code_review"), [])
    
    def add_example(
        self,
        language: str,
        task_type: str,
        input_code: str,
        expected_output: Dict[str, Any]
    ) -> None:
        """Add a new example to the cache.
        
        Args:
            language: Programming language
            task_type: Type of task
            input_code: The code snippet
            expected_output: Expected finding output
        """
        key = f"{language.lower()}_{task_type}"
        
        if key not in self._examples_cache:
            self._examples_cache[key] = []
        
        self._examples_cache[key].append({
            "language": language,
            "input_code": input_code,
            "expected_output": expected_output
        })
    
    def save_examples(self, language: str, task_type: str) -> None:
        """Save examples to a JSON file.
        
        Args:
            language: Programming language
            task_type: Type of task
        """
        key = f"{language.lower()}_{task_type}"
        examples = self._examples_cache.get(key, [])
        
        if not examples:
            return
        
        self.examples_dir.mkdir(parents=True, exist_ok=True)
        file_path = self.examples_dir / f"{key}.json"
        
        with open(file_path, 'w') as f:
            json.dump({"examples": examples}, f, indent=2)
