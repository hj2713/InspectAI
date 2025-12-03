"""Codebase Indexer - Parses and indexes repository structure.

This module provides AST parsing for Python, Java, and C++ files,
storing the parsed structure in Supabase for intelligent PR reviews.

Features:
- Background async indexing (non-blocking)
- Per-project isolation
- Incremental updates (only changed files)
- Call graph extraction
- Import/dependency tracking
"""

import os
import ast
import hashlib
import asyncio
import logging
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# ============================================
# Data Classes
# ============================================

@dataclass
class ParsedSymbol:
    """Represents a parsed code symbol (function, class, etc.)"""
    name: str
    symbol_type: str  # function, class, method, variable
    qualified_name: str
    start_line: int
    end_line: int
    signature: Optional[str] = None
    parameters: List[Dict] = field(default_factory=list)
    return_type: Optional[str] = None
    docstring: Optional[str] = None
    parent_name: Optional[str] = None
    is_public: bool = True
    is_static: bool = False
    is_async: bool = False


@dataclass
class ParsedImport:
    """Represents a parsed import statement"""
    statement: str
    module: str
    names: List[str]
    is_relative: bool
    line_number: int


@dataclass
class ParsedCall:
    """Represents a function/method call"""
    callee_name: str
    caller_name: Optional[str]
    line_number: int
    call_type: str = "function"


@dataclass
class ParsedFile:
    """Represents a fully parsed file"""
    file_path: str
    language: str
    content_hash: str
    line_count: int
    symbols: List[ParsedSymbol]
    imports: List[ParsedImport]
    calls: List[ParsedCall]


# ============================================
# Python Parser
# ============================================

class PythonParser:
    """AST-based parser for Python files."""
    
    def parse(self, file_path: str, content: str) -> ParsedFile:
        """Parse a Python file and extract structure."""
        try:
            tree = ast.parse(content, filename=file_path)
        except SyntaxError as e:
            logger.warning(f"Syntax error in {file_path}: {e}")
            return ParsedFile(
                file_path=file_path,
                language="python",
                content_hash=self._hash_content(content),
                line_count=content.count('\n') + 1,
                symbols=[],
                imports=[],
                calls=[]
            )
        
        symbols = []
        imports = []
        calls = []
        
        # Extract imports
        imports = self._extract_imports(tree)
        
        # Extract symbols and calls
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                symbols.append(self._parse_function(node, file_path))
                calls.extend(self._extract_calls_from_function(node))
            elif isinstance(node, ast.AsyncFunctionDef):
                symbols.append(self._parse_async_function(node, file_path))
                calls.extend(self._extract_calls_from_function(node))
            elif isinstance(node, ast.ClassDef):
                class_symbol, method_symbols = self._parse_class(node, file_path)
                symbols.append(class_symbol)
                symbols.extend(method_symbols)
        
        return ParsedFile(
            file_path=file_path,
            language="python",
            content_hash=self._hash_content(content),
            line_count=content.count('\n') + 1,
            symbols=symbols,
            imports=imports,
            calls=calls
        )
    
    def _extract_imports(self, tree: ast.AST) -> List[ParsedImport]:
        """Extract all import statements."""
        imports = []
        
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(ParsedImport(
                        statement=f"import {alias.name}",
                        module=alias.name.split('.')[0],
                        names=[alias.name],
                        is_relative=False,
                        line_number=node.lineno
                    ))
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = [alias.name for alias in node.names]
                is_relative = node.level > 0
                
                if is_relative:
                    stmt = f"from {'.' * node.level}{module} import {', '.join(names)}"
                else:
                    stmt = f"from {module} import {', '.join(names)}"
                
                imports.append(ParsedImport(
                    statement=stmt,
                    module=module,
                    names=names,
                    is_relative=is_relative,
                    line_number=node.lineno
                ))
        
        return imports
    
    def _parse_function(self, node: ast.FunctionDef, file_path: str) -> ParsedSymbol:
        """Parse a function definition."""
        params = []
        for arg in node.args.args:
            param = {"name": arg.arg}
            if arg.annotation:
                param["type"] = ast.unparse(arg.annotation)
            params.append(param)
        
        return_type = None
        if node.returns:
            return_type = ast.unparse(node.returns)
        
        # Build signature
        param_str = ", ".join(
            f"{p['name']}: {p.get('type', 'Any')}" if 'type' in p else p['name']
            for p in params
        )
        signature = f"def {node.name}({param_str})"
        if return_type:
            signature += f" -> {return_type}"
        
        return ParsedSymbol(
            name=node.name,
            symbol_type="function",
            qualified_name=f"{Path(file_path).stem}.{node.name}",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=signature,
            parameters=params,
            return_type=return_type,
            docstring=ast.get_docstring(node),
            is_public=not node.name.startswith('_'),
            is_async=False
        )
    
    def _parse_async_function(self, node: ast.AsyncFunctionDef, file_path: str) -> ParsedSymbol:
        """Parse an async function definition."""
        symbol = self._parse_function(
            ast.FunctionDef(
                name=node.name,
                args=node.args,
                body=node.body,
                decorator_list=node.decorator_list,
                returns=node.returns,
                lineno=node.lineno,
                end_lineno=node.end_lineno
            ),
            file_path
        )
        symbol.is_async = True
        symbol.signature = "async " + symbol.signature
        return symbol
    
    def _parse_class(self, node: ast.ClassDef, file_path: str) -> Tuple[ParsedSymbol, List[ParsedSymbol]]:
        """Parse a class definition and its methods."""
        # Class symbol
        bases = [ast.unparse(base) for base in node.bases]
        signature = f"class {node.name}"
        if bases:
            signature += f"({', '.join(bases)})"
        
        class_symbol = ParsedSymbol(
            name=node.name,
            symbol_type="class",
            qualified_name=f"{Path(file_path).stem}.{node.name}",
            start_line=node.lineno,
            end_line=node.end_lineno or node.lineno,
            signature=signature,
            docstring=ast.get_docstring(node),
            is_public=not node.name.startswith('_')
        )
        
        # Method symbols
        methods = []
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                method = self._parse_function(item, file_path) if isinstance(item, ast.FunctionDef) else self._parse_async_function(item, file_path)
                method.symbol_type = "method"
                method.qualified_name = f"{Path(file_path).stem}.{node.name}.{item.name}"
                method.parent_name = node.name
                
                # Check for static/class methods
                for decorator in item.decorator_list:
                    if isinstance(decorator, ast.Name):
                        if decorator.id == "staticmethod":
                            method.is_static = True
                        elif decorator.id == "classmethod":
                            method.is_static = True
                
                methods.append(method)
        
        return class_symbol, methods
    
    def _extract_calls_from_function(self, node: ast.AST) -> List[ParsedCall]:
        """Extract function calls from a function body."""
        calls = []
        caller_name = node.name if hasattr(node, 'name') else None
        
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                callee_name = self._get_call_name(child)
                if callee_name:
                    calls.append(ParsedCall(
                        callee_name=callee_name,
                        caller_name=caller_name,
                        line_number=child.lineno,
                        call_type="method" if "." in callee_name else "function"
                    ))
        
        return calls
    
    def _get_call_name(self, node: ast.Call) -> Optional[str]:
        """Extract the name of a function call."""
        if isinstance(node.func, ast.Name):
            return node.func.id
        elif isinstance(node.func, ast.Attribute):
            # Handle method calls like obj.method()
            parts = []
            current = node.func
            while isinstance(current, ast.Attribute):
                parts.append(current.attr)
                current = current.value
            if isinstance(current, ast.Name):
                parts.append(current.id)
            parts.reverse()
            return ".".join(parts)
        return None
    
    def _hash_content(self, content: str) -> str:
        """Generate SHA256 hash of content."""
        return hashlib.sha256(content.encode()).hexdigest()


# ============================================
# Java Parser (Basic - without tree-sitter)
# ============================================

class JavaParser:
    """Regex-based parser for Java files.
    
    Note: For production, consider using tree-sitter-java for better accuracy.
    This is a simplified implementation that handles common patterns.
    """
    
    import re
    
    # Patterns for Java parsing
    CLASS_PATTERN = re.compile(
        r'(?:public\s+)?(?:abstract\s+)?(?:final\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?(?:\s+implements\s+[\w,\s]+)?\s*\{',
        re.MULTILINE
    )
    
    METHOD_PATTERN = re.compile(
        r'(?:public|private|protected)?\s*(?:static\s+)?(?:final\s+)?(?:synchronized\s+)?(\w+(?:<[\w,\s<>]+>)?)\s+(\w+)\s*\(([^)]*)\)\s*(?:throws\s+[\w,\s]+)?\s*\{',
        re.MULTILINE
    )
    
    IMPORT_PATTERN = re.compile(
        r'^import\s+(static\s+)?([\w.]+(?:\.\*)?);',
        re.MULTILINE
    )
    
    CALL_PATTERN = re.compile(
        r'(\w+(?:\.\w+)*)\s*\(',
        re.MULTILINE
    )
    
    def parse(self, file_path: str, content: str) -> ParsedFile:
        """Parse a Java file and extract structure."""
        symbols = []
        imports = []
        calls = []
        lines = content.split('\n')
        
        # Extract imports
        for match in self.IMPORT_PATTERN.finditer(content):
            is_static = match.group(1) is not None
            import_path = match.group(2)
            module = import_path.rsplit('.', 1)[0] if '.' in import_path else import_path
            
            imports.append(ParsedImport(
                statement=match.group(0),
                module=module,
                names=[import_path.split('.')[-1]],
                is_relative=False,
                line_number=content[:match.start()].count('\n') + 1
            ))
        
        # Extract classes
        for match in self.CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            start_line = content[:match.start()].count('\n') + 1
            
            # Find class end (simplified - counts braces)
            end_line = self._find_block_end(content, match.end())
            
            symbols.append(ParsedSymbol(
                name=class_name,
                symbol_type="class",
                qualified_name=f"{Path(file_path).stem}.{class_name}",
                start_line=start_line,
                end_line=end_line,
                signature=f"class {class_name}",
                is_public="public" in match.group(0)
            ))
        
        # Extract methods
        for match in self.METHOD_PATTERN.finditer(content):
            return_type = match.group(1)
            method_name = match.group(2)
            params_str = match.group(3)
            
            # Skip constructors (return type == method name) if they're just class names
            if return_type == method_name:
                continue
            
            start_line = content[:match.start()].count('\n') + 1
            end_line = self._find_block_end(content, match.end())
            
            # Parse parameters
            params = []
            if params_str.strip():
                for param in params_str.split(','):
                    parts = param.strip().split()
                    if len(parts) >= 2:
                        params.append({
                            "type": parts[-2],
                            "name": parts[-1]
                        })
            
            signature = f"{return_type} {method_name}({params_str.strip()})"
            
            symbols.append(ParsedSymbol(
                name=method_name,
                symbol_type="method",
                qualified_name=f"{Path(file_path).stem}.{method_name}",
                start_line=start_line,
                end_line=end_line,
                signature=signature,
                parameters=params,
                return_type=return_type,
                is_public="public" in content[max(0, match.start()-50):match.start()],
                is_static="static" in content[max(0, match.start()-50):match.start()]
            ))
        
        # Extract calls (simplified)
        for match in self.CALL_PATTERN.finditer(content):
            callee = match.group(1)
            # Skip common keywords
            if callee.lower() in ['if', 'while', 'for', 'switch', 'catch', 'new', 'return']:
                continue
            
            calls.append(ParsedCall(
                callee_name=callee,
                caller_name=None,  # Would need more context
                line_number=content[:match.start()].count('\n') + 1,
                call_type="method" if "." in callee else "function"
            ))
        
        return ParsedFile(
            file_path=file_path,
            language="java",
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            line_count=len(lines),
            symbols=symbols,
            imports=imports,
            calls=calls
        )
    
    def _find_block_end(self, content: str, start: int) -> int:
        """Find the end line of a code block by counting braces."""
        brace_count = 1
        pos = start
        
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        return content[:pos].count('\n') + 1


# ============================================
# C++ Parser (Basic - without tree-sitter)
# ============================================

class CppParser:
    """Regex-based parser for C++ files.
    
    Note: For production, consider using tree-sitter-cpp for better accuracy.
    This is a simplified implementation that handles common patterns.
    """
    
    import re
    
    # Patterns for C++ parsing
    CLASS_PATTERN = re.compile(
        r'(?:class|struct)\s+(\w+)(?:\s*:\s*(?:public|private|protected)\s+\w+)?\s*\{',
        re.MULTILINE
    )
    
    FUNCTION_PATTERN = re.compile(
        r'(?:virtual\s+)?(?:static\s+)?(?:inline\s+)?(\w+(?:<[\w,\s<>]+>)?(?:\s*[*&])?)\s+(\w+)\s*\(([^)]*)\)\s*(?:const)?\s*(?:override)?\s*(?:=\s*(?:0|default|delete))?\s*[{;]',
        re.MULTILINE
    )
    
    INCLUDE_PATTERN = re.compile(
        r'^#include\s+[<"]([^>"]+)[>"]',
        re.MULTILINE
    )
    
    CALL_PATTERN = re.compile(
        r'(\w+(?:::\w+)*)\s*\(',
        re.MULTILINE
    )
    
    def parse(self, file_path: str, content: str) -> ParsedFile:
        """Parse a C++ file and extract structure."""
        symbols = []
        imports = []
        calls = []
        lines = content.split('\n')
        
        # Extract includes
        for match in self.INCLUDE_PATTERN.finditer(content):
            include_path = match.group(1)
            
            imports.append(ParsedImport(
                statement=match.group(0),
                module=include_path,
                names=[include_path.split('/')[-1].split('.')[0]],
                is_relative='"' in match.group(0),
                line_number=content[:match.start()].count('\n') + 1
            ))
        
        # Extract classes/structs
        for match in self.CLASS_PATTERN.finditer(content):
            class_name = match.group(1)
            start_line = content[:match.start()].count('\n') + 1
            end_line = self._find_block_end(content, match.end())
            
            symbols.append(ParsedSymbol(
                name=class_name,
                symbol_type="class",
                qualified_name=f"{Path(file_path).stem}.{class_name}",
                start_line=start_line,
                end_line=end_line,
                signature=f"class {class_name}"
            ))
        
        # Extract functions
        for match in self.FUNCTION_PATTERN.finditer(content):
            return_type = match.group(1)
            func_name = match.group(2)
            params_str = match.group(3)
            
            # Skip constructors/destructors
            if return_type == func_name or func_name.startswith('~'):
                continue
            
            start_line = content[:match.start()].count('\n') + 1
            
            # Check if declaration or definition
            if content[match.end()-1] == ';':
                end_line = start_line
            else:
                end_line = self._find_block_end(content, match.end())
            
            # Parse parameters
            params = []
            if params_str.strip():
                for param in params_str.split(','):
                    parts = param.strip().split()
                    if parts:
                        params.append({
                            "type": ' '.join(parts[:-1]) if len(parts) > 1 else "auto",
                            "name": parts[-1].strip('*&')
                        })
            
            symbols.append(ParsedSymbol(
                name=func_name,
                symbol_type="function",
                qualified_name=f"{Path(file_path).stem}.{func_name}",
                start_line=start_line,
                end_line=end_line,
                signature=f"{return_type} {func_name}({params_str.strip()})",
                parameters=params,
                return_type=return_type,
                is_static="static" in content[max(0, match.start()-50):match.start()]
            ))
        
        # Extract calls
        for match in self.CALL_PATTERN.finditer(content):
            callee = match.group(1)
            # Skip common keywords
            if callee.lower() in ['if', 'while', 'for', 'switch', 'catch', 'new', 'delete', 'return', 'sizeof']:
                continue
            
            calls.append(ParsedCall(
                callee_name=callee,
                caller_name=None,
                line_number=content[:match.start()].count('\n') + 1,
                call_type="method" if "::" in callee else "function"
            ))
        
        return ParsedFile(
            file_path=file_path,
            language="cpp",
            content_hash=hashlib.sha256(content.encode()).hexdigest(),
            line_count=len(lines),
            symbols=symbols,
            imports=imports,
            calls=calls
        )
    
    def _find_block_end(self, content: str, start: int) -> int:
        """Find the end line of a code block by counting braces."""
        brace_count = 1
        pos = start
        
        while pos < len(content) and brace_count > 0:
            if content[pos] == '{':
                brace_count += 1
            elif content[pos] == '}':
                brace_count -= 1
            pos += 1
        
        return content[:pos].count('\n') + 1


# ============================================
# Parser Factory
# ============================================

class CodeParserFactory:
    """Factory for creating language-specific parsers."""
    
    LANGUAGE_EXTENSIONS = {
        '.py': 'python',
        '.pyw': 'python',
        '.java': 'java',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'cpp',  # Treat C as C++
        '.h': 'cpp',
        '.hpp': 'cpp',
        '.hxx': 'cpp',
    }
    
    PARSERS = {
        'python': PythonParser,
        'java': JavaParser,
        'cpp': CppParser,
    }
    
    @classmethod
    def get_language(cls, file_path: str) -> Optional[str]:
        """Determine language from file extension."""
        ext = Path(file_path).suffix.lower()
        return cls.LANGUAGE_EXTENSIONS.get(ext)
    
    @classmethod
    def get_parser(cls, language: str):
        """Get parser for a specific language."""
        parser_class = cls.PARSERS.get(language)
        if parser_class:
            return parser_class()
        return None
    
    @classmethod
    def is_supported(cls, file_path: str) -> bool:
        """Check if file type is supported."""
        return cls.get_language(file_path) is not None
    
    @classmethod
    def parse_file(cls, file_path: str, content: str) -> Optional[ParsedFile]:
        """Parse a file using the appropriate parser."""
        language = cls.get_language(file_path)
        if not language:
            return None
        
        parser = cls.get_parser(language)
        if not parser:
            return None
        
        try:
            return parser.parse(file_path, content)
        except Exception as e:
            logger.error(f"Error parsing {file_path}: {e}")
            return None
