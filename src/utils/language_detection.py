from typing import Optional

def detect_language(filename: Optional[str]) -> str:
    """Detect programming language based on file extension.
    
    Args:
        filename: Name of the file
        
    Returns:
        Language name (e.g., "Python", "JavaScript") or "code" if unknown
    """
    if not filename:
        return "code"
        
    filename = filename.lower()
    
    extension_map = {
        ".py": "Python",
        ".js": "JavaScript",
        ".jsx": "JavaScript",
        ".ts": "TypeScript",
        ".tsx": "TypeScript",
        ".html": "HTML",
        ".css": "CSS",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".h": "C/C++ Header",
        ".go": "Go",
        ".rs": "Rust",
        ".php": "PHP",
        ".rb": "Ruby",
        ".sh": "Shell Script",
        ".bash": "Shell Script",
        ".sql": "SQL",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".md": "Markdown",
        ".xml": "XML"
    }
    
    for ext, lang in extension_map.items():
        if filename.endswith(ext):
            return lang
            
    return "code"
