"""Structured prompt builder for LLM code reviews.

Constructs well-organized prompts with:
- Clear role definition
- Structured context (parsed diffs)
- Task-specific instructions
- Few-shot examples
- Output schema
"""
import json
import re
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional
from enum import Enum


class TaskType(Enum):
    """Types of code review tasks."""
    CODE_REVIEW = "code_review"
    BUG_DETECTION = "bug_detection"
    SECURITY_AUDIT = "security_audit"
    REFACTOR = "refactor"


class ChangeType(Enum):
    """Types of code changes in a diff."""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    CONTEXT = "context"


@dataclass
class DiffChange:
    """Represents a single line change in a diff."""
    line_number: int
    change_type: ChangeType
    code: str
    old_line_number: Optional[int] = None  # For modified lines


@dataclass
class StructuredContext:
    """Structured context for code review."""
    file_path: str
    language: str
    changes: List[DiffChange]
    full_content: Optional[str] = None
    pr_title: Optional[str] = None
    pr_description: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "file_path": self.file_path,
            "language": self.language,
            "changes": [
                {
                    "line": c.line_number,
                    "type": c.change_type.value,
                    "code": c.code
                }
                for c in self.changes
            ],
            "total_changes": len(self.changes),
            "added_lines": sum(1 for c in self.changes if c.change_type == ChangeType.ADDED),
            "removed_lines": sum(1 for c in self.changes if c.change_type == ChangeType.REMOVED)
        }


# =============================================================================
# LANGUAGE-SPECIFIC CODE REVIEW RULES
# Focus: Real bugs junior developers make that cause production issues
# =============================================================================

LANGUAGE_INSTRUCTIONS = {
    "python": [
        # Memory & Mutability Bugs (very common, hard to debug)
        "MUTABLE DEFAULT ARGS: Flag `def func(items=[])` or `def func(data={})` - these share state across calls causing mysterious bugs. Fix: use `items=None` then `items = items or []`",
        
        # Exception Handling (juniors often get this wrong)
        "BARE EXCEPT: Flag `except:` or `except Exception:` that swallows all errors silently. Must catch specific exceptions (ValueError, KeyError, etc.) and log/handle appropriately",
        "EXCEPTION SWALLOWING: Flag `except SomeError: pass` - exceptions should be logged or re-raised, never silently ignored",
        
        # Resource Management (causes memory leaks in production)
        "FILE HANDLES: Flag `f = open()` without context manager. Must use `with open() as f:` to ensure file closure even on exceptions",
        "UNCLOSED RESOURCES: Check database connections, HTTP sessions, socket connections are properly closed with context managers or try/finally",
        
        # Type & None Safety (causes runtime crashes)
        "NONE CHECKS: Before calling `.attribute` or `[index]` on a variable that could be None, verify null check exists. Common in: API responses, dict.get(), function returns",
        "TYPE COERCION: Flag `int(user_input)` or `float(value)` without try/except - will crash on invalid input",
        
        # Logic Errors (subtle bugs)
        "BOOLEAN LOGIC: Check for inverted conditions: `if not x == y` should be `if x != y`. Watch for De Morgan's law violations in complex conditions",
        "COMPARISON CHAINS: Flag `if x == 1 or 2 or 3` (always True!) - should be `if x in (1, 2, 3)` or `if x == 1 or x == 2 or x == 3`",
        "IDENTITY VS EQUALITY: Flag `if x is []` or `if x is {}` - use `==` for value comparison, `is` only for None/True/False/singletons",
        
        # Iteration & Loop Bugs
        "MODIFYING WHILE ITERATING: Flag `for item in list: list.remove(item)` - causes skipped elements. Use list comprehension or iterate over copy",
        "OFF-BY-ONE: In slicing `list[start:end]`, end is exclusive. Check range() bounds in loops. Flag `range(1, len(arr))` when 0 should be included",
        
        # Async Pitfalls
        "ASYNC WITHOUT AWAIT: Flag async functions that don't await other async calls - results in unawaited coroutines that never execute",
        "BLOCKING IN ASYNC: Flag `time.sleep()`, `requests.get()`, file I/O in async functions - blocks entire event loop. Use `asyncio.sleep()`, `aiohttp`, `aiofiles`",
        
        # String & Encoding
        "STRING FORMATTING INJECTION: Flag `query = f\"SELECT * FROM users WHERE id = {user_id}\"` - SQL injection. Use parameterized queries",
        "ENCODING ERRORS: When reading files with non-ASCII content, specify encoding: `open(f, encoding='utf-8')` to avoid UnicodeDecodeError"
    ],
    
    "javascript": [
        # Equality & Type Coercion (most common JS bug)
        "LOOSE EQUALITY: Flag every `==` and `!=` - must use `===` and `!==`. Examples: `0 == ''` is true, `null == undefined` is true, causes subtle bugs",
        "FALSY CONFUSION: `if (value)` fails for 0, '', [], NaN. For checking existence use `if (value !== undefined && value !== null)` or `if (value != null)`",
        
        # Async/Promise Bugs (juniors struggle with these)
        "FLOATING PROMISES: Flag async function calls without `await` or `.then()/.catch()` - errors are silently swallowed, operations may not complete",
        "MISSING CATCH: Every `.then()` chain needs `.catch()` at the end. Flag Promise chains without error handling",
        "ASYNC IN LOOP: Flag `array.forEach(async (item) => {...})` - doesn't wait for completion. Use `for...of` with await or `Promise.all(array.map(...))`",
        "RACE CONDITIONS: Flag code that assumes async operations complete in order without explicit synchronization",
        
        # Null/Undefined Safety
        "PROPERTY ACCESS ON NULL: Before `obj.property` or `obj.method()`, check if obj exists. Use optional chaining `obj?.property` or explicit checks",
        "ARRAY BOUNDS: `array[index]` returns undefined for out-of-bounds, not error. Verify index < array.length before access",
        "DESTRUCTURING DEFAULTS: Flag `const {a, b} = maybeNull` - crashes if null. Use `const {a, b} = maybeNull || {}` or optional chaining",
        
        # Scope & Closure Bugs
        "VAR IN LOOPS: Flag `for (var i...)` - var is function-scoped, causes closure bugs. Must use `let` for block scoping",
        "CLOSURE CAPTURE: In loops creating callbacks, captured variables share final value. Use `let`, IIFE, or `forEach` to create proper closures",
        "THIS BINDING: In callbacks and event handlers, `this` may not be what you expect. Flag class methods passed as callbacks without `.bind(this)` or arrow functions",
        
        # Object/Array Mutations
        "UNINTENDED MUTATION: Flag direct modification of function parameters or state. Use spread `{...obj}` or `[...arr]` to clone before modifying",
        "REFERENCE COMPARISON: Flag `if (arr1 === arr2)` or `if (obj1 === obj2)` for value comparison - compares references, not contents",
        
        # Type Safety
        "NUMBER PARSING: `parseInt('08')` may fail in old browsers, always specify radix: `parseInt('08', 10)`. `parseFloat('10abc')` returns 10, not NaN",
        "NAN CHECKS: `NaN === NaN` is false! Use `Number.isNaN(value)` or `isNaN(value)` to check for NaN",
        
        # Event & Memory Leaks
        "EVENT LISTENER LEAKS: Every `addEventListener` needs corresponding `removeEventListener` on cleanup, especially in SPAs/React components",
        "TIMER LEAKS: `setInterval` must be cleared with `clearInterval`. In React/Vue, clear in cleanup/unmount"
    ],
    
    "typescript": [
        # Type Safety Violations
        "ANY ESCAPE HATCH: Flag every `any` type - defeats TypeScript's purpose. Use `unknown` for truly unknown types, then narrow with type guards",
        "TYPE ASSERTION ABUSE: Flag `as SomeType` without runtime validation - crashes if assumption is wrong. Prefer type guards: `if ('prop' in obj)`",
        "NON-NULL ASSERTION: Flag `value!` (non-null assertion) - tells compiler to trust you but crashes at runtime if null. Add proper null checks instead",
        
        # Null Safety (even with strict mode)
        "OPTIONAL CHAINING OVERUSE: `obj?.prop?.method?.()` may silently return undefined. Ensure you handle the undefined case explicitly",
        "STRICT NULL VIOLATIONS: After `if (value)` check, value is narrowed. But reassignment loses narrowing - re-check after any modification",
        
        # Generic & Interface Issues
        "GENERIC INFERENCE FAILURE: When TS can't infer generic type, it defaults to `unknown` or `{}`. Provide explicit type arguments: `func<MyType>()`",
        "INTERFACE VS TYPE: For extendable object shapes use `interface`. For unions, intersections, mapped types use `type`. Don't mix inconsistently",
        
        # Async Type Issues
        "PROMISE TYPE: Function returning Promise should be typed `Promise<ReturnType>`. Flag `async function(): any` - loses type safety on await",
        "VOID VS UNDEFINED: `void` means return value should be ignored. For functions that may return undefined, use `undefined` type explicitly",
        
        # All JavaScript rules also apply
        "JS RULES APPLY: All JavaScript rules about equality, async, null safety, closures apply - TypeScript doesn't fix runtime behavior"
    ],
    
    "java": [
        # NullPointerException Prevention (most common Java bug)
        "NULL CHECKS: Before any method call or field access on an object, verify it's not null. Flag `obj.method()` where obj comes from: method params, Optional.get(), Map.get(), external APIs",
        "OPTIONAL MISUSE: Flag `optional.get()` without `isPresent()` check - defeats purpose of Optional. Use `orElse()`, `orElseThrow()`, `ifPresent()`, or `map()`",
        "STRING COMPARISON: Flag `str1 == str2` for String comparison - compares references. Must use `str1.equals(str2)`. Also null-safe: `Objects.equals(str1, str2)`",
        
        # Resource Leaks (causes production memory issues)
        "TRY-WITH-RESOURCES: Flag any `new FileInputStream()`, `new Connection()`, `new BufferedReader()` not in try-with-resources. Resources must be auto-closed",
        "STREAM CLOSURE: All Java Streams from I/O operations must be closed. Use try-with-resources for streams from Files.lines(), etc.",
        "CONNECTION POOLS: Database connections from pool must be returned (closed). Unclosed connections exhaust the pool",
        
        # Exception Anti-Patterns
        "CATCH AND IGNORE: Flag `catch (Exception e) {}` or `catch (Exception e) { e.printStackTrace(); }` in production code - must log properly and handle",
        "CATCHING EXCEPTION: Flag `catch (Exception e)` - too broad. Catch specific exceptions. Never catch Error or Throwable in application code",
        "EXCEPTION IN FINALLY: Code in finally block should not throw - can suppress original exception. Wrap in try-catch if risky",
        
        # Concurrency Bugs
        "THREAD SAFETY: Mutable fields accessed by multiple threads need synchronization. Flag shared mutable state without volatile, synchronized, or concurrent collections",
        "CHECK-THEN-ACT: Flag `if (map.containsKey(k)) { return map.get(k); }` in concurrent code - race condition. Use `computeIfAbsent()` or `putIfAbsent()`",
        "DOUBLE-CHECKED LOCKING: If implementing singleton with double-checked locking, field must be volatile or it's broken on some JVMs",
        
        # Collection Pitfalls
        "CONCURRENT MODIFICATION: Flag iteration over collection while modifying it - causes ConcurrentModificationException. Use Iterator.remove() or collect changes separately",
        "ARRAYLIST VS LINKEDLIST: ArrayList for random access, LinkedList for frequent insert/delete. Wrong choice causes O(n) instead of O(1) operations",
        
        # Equals/HashCode Contract
        "EQUALS WITHOUT HASHCODE: If you override equals(), you MUST override hashCode(). Objects that are equal must have same hash code",
        "INSTANCEOF IN EQUALS: Proper equals() should handle null and use instanceof or getClass() check"
    ],
    
    "go": [
        # Error Handling (most critical Go pattern)
        "UNCHECKED ERRORS: Flag any function call that returns error where error is assigned to `_` or not checked. Pattern: `result, err := func(); if err != nil { return err }`",
        "ERROR SHADOWING: Flag `err := ...` inside if/for blocks when outer err exists - shadows and loses original error. Use `err = ...` (no colon)",
        "ERROR WRAPPING: When returning errors up the stack, wrap with context: `fmt.Errorf(\"failed to X: %w\", err)` to preserve error chain",
        
        # Nil Safety
        "NIL POINTER: Before dereferencing pointer (`*p` or `p.field`), check for nil. Flag pointer dereference where nil is possible (from map lookup, type assertion, function return)",
        "NIL SLICE/MAP: Nil slice can be appended to, but nil map panics on write. Always `make(map[K]V)` before writing to map",
        "INTERFACE NIL CHECK: `if i == nil` only works if both value AND type are nil. An interface holding nil pointer is NOT nil. Check: `if i == nil || reflect.ValueOf(i).IsNil()`",
        
        # Concurrency Bugs
        "GOROUTINE LEAKS: Every goroutine must have exit condition. Flag `go func()` without done channel, context cancellation, or clear termination path",
        "CHANNEL DEADLOCK: Unbuffered channel blocks until receiver ready. Flag `ch <- value` without guaranteed receiver - causes deadlock",
        "RACE CONDITIONS: Flag shared variable access across goroutines without mutex, channel, or atomic operations. Run `go test -race` to detect",
        "CLOSURE CAPTURE IN GOROUTINE: Flag `for i := range items { go func() { use(i) }() }` - all goroutines see final value. Pass as param: `go func(i int) {...}(i)`",
        
        # Defer Pitfalls
        "DEFER IN LOOP: Flag `for { f := open(); defer f.Close() }` - defers stack up until function returns, causing resource exhaustion. Close explicitly in loop",
        "DEFER EVALUATION: Defer args evaluated immediately, not when deferred. Flag `defer log.Printf(\"x=%d\", x)` if x changes - capture x first or use closure",
        
        # Slice & Map Gotchas
        "SLICE APPEND: `append()` may return new slice. Always `slice = append(slice, elem)`. Flag `append(slice, elem)` without assignment",
        "MAP ITERATION ORDER: Map iteration order is random. Flag code that depends on consistent map iteration order",
        "SLICE BACKING ARRAY: Slicing `a[1:3]` shares backing array with a. Modifications affect original. Use `copy()` for independent slice",
        
        # Type Assertions
        "UNCHECKED TYPE ASSERTION: Flag `value.(Type)` without comma-ok idiom. Panics if wrong type. Use `v, ok := value.(Type); if ok { ... }`"
    ],
    
    "rust": [
        # Ownership & Borrowing (what juniors struggle with)
        "BORROW CHECKER: When compiler complains about borrows, don't just clone everything. Understand lifetime requirements and restructure code",
        "MOVE AFTER USE: After moving ownership (passing by value), original is invalid. If you need to use value again, clone before move or pass reference",
        
        # Error Handling
        "UNWRAP ABUSE: Flag every `.unwrap()` and `.expect()` - they panic on None/Err. In libraries use `?` operator. In apps, handle errors gracefully",
        "PANIC IN LIBRARY: Library code should return Result, never panic. Flag `panic!()`, `unwrap()`, `expect()` in lib code - let caller decide how to handle",
        
        # Option/Result Patterns
        "OPTION CHAINING: Use `map()`, `and_then()`, `unwrap_or_default()` instead of manual match for simple Option operations",
        "RESULT PROPAGATION: Use `?` operator to propagate errors instead of nested matches. Ensure function signature returns compatible Result",
        
        # Memory Safety
        "UNSAFE BLOCKS: Flag every `unsafe` block - must have comment explaining why it's safe. Verify invariants are actually maintained",
        "RAW POINTERS: When using raw pointers in unsafe code, verify pointer validity, alignment, and that no aliasing rules are violated",
        
        # Concurrency
        "SEND/SYNC: Types shared across threads must implement Send+Sync. Compiler usually catches this, but verify when using unsafe",
        "DEADLOCK: With multiple Mutexes, always acquire in consistent order across all code paths to prevent deadlock"
    ],
    
    "c": [
        # Memory Management (most critical C issues)
        "MEMORY LEAKS: Every malloc/calloc must have corresponding free. Track allocation and verify all paths (including error paths) free memory",
        "USE AFTER FREE: After free(ptr), set ptr = NULL. Never access freed memory - undefined behavior, security vulnerability",
        "DOUBLE FREE: Freeing same pointer twice is undefined behavior. Set to NULL after free to make double-free a no-op",
        "BUFFER OVERFLOW: Check array bounds before access. strcpy, sprintf, gets are DANGEROUS - use strncpy, snprintf, fgets with size limits",
        
        # Pointer Safety
        "NULL POINTER: Check pointers before dereference. Function params, malloc return, and any pointer from external source may be NULL",
        "DANGLING POINTER: Don't return pointer to local variable - memory invalid after function returns",
        "UNINITIALIZED: Local variables aren't zero-initialized. Always initialize: `int x = 0;` not just `int x;`",
        
        # String Handling
        "STRING TERMINATION: C strings must be null-terminated. After strncpy, manually add '\\0' if source may be longer than dest",
        "FORMAT STRING: Flag `printf(user_input)` - format string vulnerability. Always `printf(\"%s\", user_input)`",
        
        # Integer Issues
        "INTEGER OVERFLOW: Check arithmetic won't overflow before performing. `if (a > INT_MAX - b)` before `a + b`",
        "SIGNED/UNSIGNED: Comparing signed and unsigned can give wrong results. Be explicit about types, especially in size calculations"
    ],
    
    "cpp": [
        # Modern C++ Safety (avoid C-style bugs)
        "SMART POINTERS: Flag raw `new` without smart pointer wrapper. Use `std::make_unique`, `std::make_shared`. Raw pointers only for non-owning references",
        "RAII: Resources should be acquired in constructor, released in destructor. Flag manual resource management that could leak on exception",
        
        # Memory & Object Lifetime
        "USE AFTER MOVE: After `std::move(obj)`, obj is in valid but unspecified state. Don't use moved-from objects except to reassign",
        "DANGLING REFERENCE: Don't return reference to local variable. Don't store reference to temporary. Don't hold reference longer than referenced object",
        "VECTOR INVALIDATION: Operations like push_back, insert can invalidate iterators and references to vector elements. Re-obtain after modification",
        
        # Exception Safety
        "EXCEPTION IN DESTRUCTOR: Destructors must not throw. If they do during stack unwinding, std::terminate is called",
        "COPY-SWAP: For exception-safe assignment operator, use copy-and-swap idiom. Direct member assignment may leave object in inconsistent state",
        
        # Object-Oriented Pitfalls
        "VIRTUAL DESTRUCTOR: Base classes with virtual methods need virtual destructor. Otherwise, deleting derived via base pointer is undefined behavior",
        "SLICING: Passing derived class by value to function taking base class slices off derived parts. Use references or pointers for polymorphism",
        
        # STL Usage
        "ITERATOR SAFETY: Don't modify container while iterating. Use erase-remove idiom or collect changes to apply after iteration",
        "RESERVE FOR PERFORMANCE: When you know final size, vector.reserve() prevents multiple reallocations during push_back"
    ],
    
    "ruby": [
        # Nil Safety
        "NIL ERRORS: Before calling methods on potentially nil objects, check with `&.` (safe navigation) or explicit nil check. NoMethodError on nil is most common Ruby error",
        "BLANK VS NIL VS EMPTY: In Rails, understand difference: nil.blank? is true, \"\".blank? is true, \" \".blank? is true, [].blank? is true. Use appropriate check",
        
        # Symbol vs String
        "SYMBOL CONFUSION: Symbols are immutable identifiers, strings are mutable text. Hash keys should typically be symbols for performance: `hash[:key]` not `hash[\"key\"]`",
        
        # Block & Proc Issues
        "RETURN IN BLOCK: `return` in a block returns from enclosing method, not just the block. Use `next` to exit block with value",
        "BLOCK VS PROC: `block.call` vs `yield` - know when method expects block. &block converts block to proc. Check arity if required",
        
        # Rails Specific
        "N+1 QUERIES: In Rails, iterating associations without eager loading causes N+1 queries. Use `includes()` or `preload()` for associations",
        "MASS ASSIGNMENT: Use strong parameters in controllers. Flag direct `params[:user]` to model without permit",
        "CALLBACK GOTCHAS: after_commit vs after_save - know the difference for transaction safety. Callbacks can fail silently"
    ],
    
    "php": [
        # Type Safety
        "TYPE JUGGLING: PHP's `==` does type coercion: `\"0\" == false` is true, `0 == \"abc\"` is true. Use `===` for strict comparison",
        "NULL COALESCING: Use `??` operator for null checks: `$value = $input ?? 'default'`. Better than `isset()` ternary",
        
        # Security
        "SQL INJECTION: Flag string concatenation in queries. Use prepared statements: `$stmt = $pdo->prepare(); $stmt->execute()`",
        "XSS PREVENTION: Flag `echo $userInput`. Always `htmlspecialchars($userInput, ENT_QUOTES, 'UTF-8')` for output",
        
        # Array Issues
        "ARRAY KEY: Accessing undefined array key raises notice in PHP 8+. Use `$arr['key'] ?? null` or isset() check",
        "ARRAY FUNCTIONS: `array_merge` vs `+` operator behave differently with numeric keys. Know which preserves keys",
        
        # Object Oriented
        "CONSTRUCTOR PROMOTION: In PHP 8+, use constructor property promotion: `public function __construct(private string $name)` for cleaner code",
        "NULLABLE TYPES: Declare nullable with `?Type` or `Type|null`. Check before using potentially null values"
    ],
    
    "default": [
        # Universal Logic Errors
        "OFF-BY-ONE: Loop boundaries often wrong by 1. Check: should it be `<` or `<=`? Start at 0 or 1? Array indices are 0-based in most languages",
        "BOUNDARY CONDITIONS: Test behavior at boundaries: empty array, zero, negative numbers, null/None, max integers. Many bugs occur at edges",
        "BOOLEAN LOGIC: De Morgan's laws: `!(A && B)` = `(!A || !B)`. Incorrect negation of complex conditions is common",
        
        # Null/None Handling
        "NULL SAFETY: Before accessing properties or methods on any value that could be null/None/undefined, add explicit check",
        "EMPTY VS NULL: Distinguish between empty string/array/object and null. They require different handling",
        
        # Error Handling
        "ERROR PROPAGATION: Don't swallow errors silently. Either handle them appropriately or propagate them up with context",
        "RESOURCE CLEANUP: Files, connections, handles must be closed even on error. Use language's try-finally or context manager equivalent",
        
        # Security Basics
        "INPUT VALIDATION: Never trust user input. Validate type, format, length, and range before using",
        "SECRETS IN CODE: Flag hardcoded passwords, API keys, tokens. Must come from environment or secret management",
        "LOG SENSITIVITY: Don't log passwords, tokens, PII. Mask sensitive data in logs"
    ]
}

# =============================================================================
# SECURITY-SPECIFIC CHECKS BY LANGUAGE
# Focus: OWASP Top 10 and common vulnerability patterns
# =============================================================================

SECURITY_CHECKS = {
    "python": [
        # Injection Attacks
        "SQL INJECTION: Flag f-strings, .format(), or % in SQL queries. Use parameterized queries: `cursor.execute('SELECT * FROM users WHERE id = ?', (user_id,))`",
        "COMMAND INJECTION: Flag `os.system()`, `subprocess.run(shell=True)`, `eval()`, `exec()` with user input. Use subprocess with list args, no shell",
        "TEMPLATE INJECTION: In Jinja2/Django templates, `{{ user_input }}` is auto-escaped, but `{{ user_input|safe }}` or `{% autoescape off %}` is dangerous",
        
        # Deserialization
        "PICKLE: Never unpickle untrusted data - allows arbitrary code execution. Flag `pickle.loads(user_data)`. Use JSON or validate source",
        "YAML: `yaml.load()` is unsafe. Use `yaml.safe_load()` to prevent code execution",
        
        # Path Traversal  
        "PATH TRAVERSAL: Flag `open(user_path)` or `os.path.join(base, user_input)` without validation. User can use '../' to escape. Use `os.path.realpath()` and verify within base",
        
        # Secrets & Auth
        "HARDCODED SECRETS: Flag API keys, passwords, tokens in code. Check: AWS keys (AKIA...), JWT secrets, database passwords. Use environment variables",
        "WEAK CRYPTO: Flag MD5, SHA1 for passwords. Use bcrypt, argon2, or scrypt. Flag `random` module for security - use `secrets` module"
    ],
    
    "javascript": [
        # XSS (Cross-Site Scripting)
        "DOM XSS: Flag `innerHTML`, `outerHTML`, `document.write()`, `insertAdjacentHTML` with user data. Use `textContent` or DOM methods",
        "EVAL INJECTION: Flag `eval()`, `new Function()`, `setTimeout/setInterval` with string args. Allows arbitrary code execution",
        "HREF JAVASCRIPT: Flag `href={userInput}` in React - can execute `javascript:alert()`. Validate URL scheme is http/https",
        
        # Injection
        "SQL INJECTION: In Node.js, flag string concatenation in queries. Use parameterized queries with your database driver",
        "COMMAND INJECTION: Flag `child_process.exec()` with user input. Use `execFile()` with array args or properly escape",
        "NOSQL INJECTION: In MongoDB, flag `{$where: userInput}` or queries built with user input. Use typed queries",
        
        # Prototype Pollution
        "PROTOTYPE POLLUTION: Flag `obj[userKey] = userValue` without validating key isn't '__proto__', 'constructor', 'prototype'. Can modify Object.prototype",
        
        # Client-Side Security
        "SENSITIVE DATA EXPOSURE: Don't store secrets, tokens in localStorage/sessionStorage - accessible to XSS. Use httpOnly cookies",
        "CORS: Verify Access-Control-Allow-Origin isn't '*' with credentials. Whitelist specific origins"
    ],
    
    "java": [
        # Injection
        "SQL INJECTION: Flag string concat in SQL. Use PreparedStatement: `conn.prepareStatement(\"SELECT * FROM users WHERE id = ?\"); ps.setInt(1, userId);`",
        "LDAP INJECTION: Escape user input in LDAP queries. Use framework's parameterized LDAP search",
        "XPATH INJECTION: Don't concat user input in XPath. Use parameterized XPath APIs",
        
        # Deserialization
        "UNSAFE DESERIALIZATION: ObjectInputStream.readObject() on untrusted data allows RCE. Use look-ahead deserialization or avoid Java serialization",
        "XML EXTERNAL ENTITIES: Configure XML parsers to disable external entities. Flag `DocumentBuilderFactory` without secure settings",
        
        # Cryptography
        "WEAK ALGORITHMS: Flag DES, MD5, SHA1 for security purposes. Use AES-256, SHA-256/SHA-3",
        "PRNG: Flag `java.util.Random` for security. Use `SecureRandom` for tokens, keys, nonces",
        
        # Access Control
        "HARDCODED CREDENTIALS: Flag passwords, keys in source. Check string literals for credential patterns",
        "TRUST BOUNDARY: Validate all input from external sources before use. Don't trust HTTP headers, cookies, form fields"
    ],
    
    "go": [
        # Injection
        "SQL INJECTION: Flag `fmt.Sprintf` in SQL queries. Use `db.Query(\"SELECT * FROM users WHERE id = ?\", id)` with placeholders",
        "COMMAND INJECTION: Flag `exec.Command` with user input in command string. Pass arguments as separate strings",
        "TEMPLATE INJECTION: Use `text/template` carefully. `html/template` auto-escapes for HTML context",
        
        # Path & File
        "PATH TRAVERSAL: Flag `filepath.Join(base, userInput)` without cleaning. Use `filepath.Clean()` and verify result is under base directory",
        "FILE PERMISSIONS: When creating files, specify restrictive permissions. Flag `os.Create` for sensitive files - use `os.OpenFile` with 0600",
        
        # Crypto
        "WEAK CRYPTO: Flag `crypto/md5`, `crypto/sha1` for security. Use `crypto/sha256` or higher",
        "RANDOM: Flag `math/rand` for security. Use `crypto/rand` for secure random values"
    ],
    
    "default": [
        # OWASP Top 10 Coverage
        "INJECTION: Any user input used in SQL, commands, LDAP, OS commands, XML, or other interpreters must be parameterized/escaped",
        "BROKEN AUTH: Check session management, password handling, credential storage. No hardcoded secrets",
        "SENSITIVE DATA: Classify data, encrypt at rest and in transit. Don't log sensitive data",
        "XXE: Disable external entities in XML parsers. Use JSON when possible",
        "BROKEN ACCESS CONTROL: Every endpoint must verify user has permission for requested resource. Check both authN and authZ",
        "SECURITY MISCONFIGURATION: Check for debug mode, default credentials, verbose errors, unnecessary features enabled",
        "XSS: Escape output based on context (HTML, JS, URL, CSS). Use framework's auto-escaping",
        "INSECURE DESERIALIZATION: Don't deserialize untrusted data with native serialization. Use JSON with schema validation",
        "VULNERABLE COMPONENTS: Check dependencies for known vulnerabilities. Keep libraries updated",
        "INSUFFICIENT LOGGING: Security events should be logged. Log authentication, authorization failures, input validation failures"
    ]
}

# Output schema for consistent results
OUTPUT_SCHEMA = {
    "findings": [
        {
            "line": "number - the exact line number with the issue",
            "severity": "critical|high|medium|low",
            "category": "bug|security|performance|style|logic",
            "description": "Clear description of the issue",
            "fix_suggestion": "Specific code fix or recommendation",
            "confidence": "number 0-1 indicating confidence"
        }
    ]
}


class PromptBuilder:
    """Builds structured prompts for LLM code reviews."""
    
    def __init__(self):
        self.example_selector = None  # Will be set when needed
    
    def build_review_prompt(
        self,
        context: StructuredContext,
        task_type: TaskType = TaskType.CODE_REVIEW,
        include_examples: bool = True,
        max_examples: int = 2
    ) -> str:
        """Build a structured prompt for code review.
        
        Args:
            context: Structured context with file info and changes
            task_type: Type of review task
            include_examples: Whether to include few-shot examples
            max_examples: Maximum number of examples to include
            
        Returns:
            Structured prompt string
        """
        sections = []
        
        # 1. Role Definition
        sections.append(self._build_role_section(task_type))
        
        # 2. Task Instructions
        sections.append(self._build_instructions_section(task_type, context.language))
        
        # 3. Structured Context
        sections.append(self._build_context_section(context))
        
        # 4. Few-shot Examples (if enabled)
        if include_examples:
            examples_section = self._build_examples_section(
                context.language, 
                task_type,
                max_examples
            )
            if examples_section:
                sections.append(examples_section)
        
        # 5. Output Schema
        sections.append(self._build_output_section())
        
        # 6. Final Instructions
        sections.append(self._build_final_instructions(task_type))
        
        return "\n\n".join(sections)
    
    def _build_role_section(self, task_type: TaskType) -> str:
        """Build the role definition section."""
        roles = {
            TaskType.CODE_REVIEW: (
                "You are a **Senior Software Engineer** with 10+ years of experience "
                "conducting thorough code reviews. You focus on finding real issues that "
                "could cause bugs, security vulnerabilities, or maintenance problems. "
                "You are practical, not pedantic - you don't nitpick style preferences."
            ),
            TaskType.BUG_DETECTION: (
                "You are a **Bug Detection Specialist** expert at finding logic errors, "
                "edge cases, type mismatches, and runtime issues. You think like a QA "
                "engineer trying to break the code."
            ),
            TaskType.SECURITY_AUDIT: (
                "You are a **Security Engineer** specialized in application security. "
                "You identify vulnerabilities like injection attacks, authentication flaws, "
                "and data exposure risks. You follow OWASP guidelines."
            ),
            TaskType.REFACTOR: (
                "You are a **Software Architect** focused on code quality and maintainability. "
                "You suggest improvements for readability, performance, and design patterns "
                "without changing functionality."
            )
        }
        return f"## Role\n\n{roles.get(task_type, roles[TaskType.CODE_REVIEW])}"
    
    def _build_instructions_section(self, task_type: TaskType, language: str) -> str:
        """Build the task-specific instructions section."""
        base_instructions = {
            TaskType.CODE_REVIEW: [
                "Review ONLY the changed lines (marked as 'added' or 'modified')",
                "Do NOT comment on removed lines or unchanged context",
                "Focus on issues that could cause real problems, not style preferences",
                "Each finding MUST include the exact line number"
            ],
            TaskType.BUG_DETECTION: [
                "Scan for bugs that could cause runtime errors or incorrect behavior",
                "Check edge cases: null/None values, empty arrays, boundary conditions",
                "Look for logic errors in conditionals and loops",
                "Identify type mismatches and conversion errors"
            ],
            TaskType.SECURITY_AUDIT: [
                "Focus on security vulnerabilities that could be exploited",
                "Check for injection attacks (SQL, command, XSS)",
                "Look for authentication and authorization flaws",
                "Identify hardcoded secrets and sensitive data exposure"
            ],
            TaskType.REFACTOR: [
                "Suggest improvements that enhance readability and maintainability",
                "Identify duplicate code that could be extracted",
                "Recommend better design patterns where applicable",
                "Focus on the changed code, not the entire file"
            ]
        }
        
        # Get language-specific instructions
        lang_key = language.lower() if language.lower() in LANGUAGE_INSTRUCTIONS else "default"
        lang_instructions = LANGUAGE_INSTRUCTIONS[lang_key]
        
        # Get security checks if security audit
        security_instructions = []
        if task_type == TaskType.SECURITY_AUDIT:
            sec_key = language.lower() if language.lower() in SECURITY_CHECKS else "default"
            security_instructions = SECURITY_CHECKS[sec_key]
        
        # Combine instructions
        all_instructions = base_instructions.get(task_type, base_instructions[TaskType.CODE_REVIEW])
        
        instruction_text = "## Instructions\n\n"
        instruction_text += "**General:**\n"
        for i, inst in enumerate(all_instructions, 1):
            instruction_text += f"{i}. {inst}\n"
        
        instruction_text += f"\n**{language.capitalize()}-Specific Checks (Apply These Rules):**\n"
        # Include more rules since they're now specific and actionable
        max_rules = 8 if task_type == TaskType.BUG_DETECTION else 6
        for i, inst in enumerate(lang_instructions[:max_rules], 1):
            instruction_text += f"{i}. {inst}\n"
        
        if security_instructions:
            instruction_text += f"\n**Security Vulnerability Checks for {language.capitalize()}:**\n"
            max_sec_rules = 6 if task_type == TaskType.SECURITY_AUDIT else 3
            for i, inst in enumerate(security_instructions[:max_sec_rules], 1):
                instruction_text += f"{i}. {inst}\n"
        
        return instruction_text
    
    def _build_context_section(self, context: StructuredContext) -> str:
        """Build the structured context section."""
        context_dict = context.to_dict()
        
        section = "## Code Context\n\n"
        section += f"**File:** `{context.file_path}`\n"
        section += f"**Language:** {context.language}\n"
        section += f"**Changes:** {context_dict['added_lines']} added, {context_dict['removed_lines']} removed\n\n"
        
        # Format changes as structured data
        section += "### Changes (JSON Format)\n\n```json\n"
        section += json.dumps(context_dict["changes"], indent=2)
        section += "\n```\n"
        
        # Include full file if provided (truncated)
        if context.full_content:
            lines = context.full_content.split('\n')
            if len(lines) > 100:
                section += "\n### Full File Context (truncated)\n\n```" + context.language + "\n"
                section += '\n'.join(lines[:100])
                section += f"\n... ({len(lines) - 100} more lines)\n```\n"
            else:
                section += "\n### Full File Context\n\n```" + context.language + "\n"
                section += context.full_content
                section += "\n```\n"
        
        return section
    
    def _build_examples_section(
        self, 
        language: str, 
        task_type: TaskType,
        max_examples: int
    ) -> Optional[str]:
        """Build the few-shot examples section."""
        # Import here to avoid circular imports
        from .example_selector import ExampleSelector
        
        if self.example_selector is None:
            self.example_selector = ExampleSelector()
        
        examples = self.example_selector.get_examples(
            language=language,
            task_type=task_type.value,
            max_examples=max_examples
        )
        
        if not examples:
            return None
        
        section = "## Examples\n\n"
        section += "Here are examples of good code review findings:\n\n"
        
        for i, example in enumerate(examples, 1):
            section += f"### Example {i}\n\n"
            section += f"**Input Code:**\n```{example.get('language', language)}\n"
            section += example.get('input_code', '')
            section += "\n```\n\n"
            section += f"**Expected Finding:**\n```json\n"
            section += json.dumps(example.get('expected_output', {}), indent=2)
            section += "\n```\n\n"
        
        return section
    
    def _build_output_section(self) -> str:
        """Build the output schema section."""
        section = "## Required Output Format\n\n"
        section += "Return your findings as a JSON object with this exact schema:\n\n"
        section += "```json\n"
        section += json.dumps(OUTPUT_SCHEMA, indent=2)
        section += "\n```\n\n"
        section += "**Important:**\n"
        section += "- Return ONLY valid JSON, no markdown or explanations\n"
        section += "- Include only findings with confidence >= 0.5\n"
        section += "- If no issues found, return: `{\"findings\": []}`\n"
        section += "- Each finding MUST have all fields\n"
        
        return section
    
    def _build_final_instructions(self, task_type: TaskType) -> str:
        """Build final reminder instructions."""
        reminders = {
            TaskType.CODE_REVIEW: (
                "Remember: Focus on the CHANGED lines only. "
                "Don't suggest adding docstrings if the code intentionally removed them. "
                "Be practical - real issues only, no nitpicking."
            ),
            TaskType.BUG_DETECTION: (
                "Remember: Look for bugs that would cause actual failures. "
                "Think about edge cases the developer might have missed. "
                "Each bug should be something that could fail in production."
            ),
            TaskType.SECURITY_AUDIT: (
                "Remember: Focus on exploitable vulnerabilities. "
                "Consider how an attacker could abuse each issue. "
                "Prioritize findings that could lead to data breaches or unauthorized access."
            ),
            TaskType.REFACTOR: (
                "Remember: Suggest practical improvements that are worth the effort. "
                "Don't recommend massive rewrites for small benefits. "
                "Focus on changes that improve readability and reduce bugs."
            )
        }
        
        return f"## Final Notes\n\n{reminders.get(task_type, reminders[TaskType.CODE_REVIEW])}"


def parse_diff_to_structured(
    file_path: str,
    patch: str,
    full_content: Optional[str] = None
) -> StructuredContext:
    """Parse a git diff patch into structured context.
    
    Args:
        file_path: Path to the file
        patch: Git diff patch string
        full_content: Optional full file content
        
    Returns:
        StructuredContext object
    """
    # Detect language from file extension
    ext_to_lang = {
        '.py': 'python',
        '.js': 'javascript',
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.jsx': 'javascript',
        '.java': 'java',
        '.go': 'go',
        '.rb': 'ruby',
        '.php': 'php',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.c': 'c',
        '.cs': 'csharp',
        '.swift': 'swift',
        '.kt': 'kotlin'
    }
    
    ext = '.' + file_path.split('.')[-1] if '.' in file_path else ''
    language = ext_to_lang.get(ext.lower(), 'unknown')
    
    # Parse the patch
    changes = []
    current_line = 0
    
    if patch:
        for line in patch.split('\n'):
            # Parse hunk header: @@ -start,count +start,count @@
            hunk_match = re.match(r'^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@', line)
            if hunk_match:
                current_line = int(hunk_match.group(1))
                continue
            
            if line.startswith('+') and not line.startswith('+++'):
                changes.append(DiffChange(
                    line_number=current_line,
                    change_type=ChangeType.ADDED,
                    code=line[1:]  # Remove the + prefix
                ))
                current_line += 1
            elif line.startswith('-') and not line.startswith('---'):
                changes.append(DiffChange(
                    line_number=current_line,
                    change_type=ChangeType.REMOVED,
                    code=line[1:]  # Remove the - prefix
                ))
                # Don't increment line for removed lines
            elif not line.startswith('\\'):  # Ignore "\ No newline at end of file"
                current_line += 1
    
    return StructuredContext(
        file_path=file_path,
        language=language,
        changes=changes,
        full_content=full_content
    )
