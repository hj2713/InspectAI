"""Tests for structured prompt system."""
import pytest
from src.prompts.prompt_builder import (
    PromptBuilder, 
    StructuredContext, 
    DiffChange, 
    ChangeType,
    TaskType,
    parse_diff_to_structured
)
from src.prompts.example_selector import ExampleSelector


def test_diff_change_creation():
    """Test creating DiffChange objects."""
    change = DiffChange(
        line_number=10,
        change_type=ChangeType.ADDED,
        code="print('hello')"
    )
    assert change.line_number == 10
    assert change.change_type == ChangeType.ADDED
    assert change.code == "print('hello')"


def test_structured_context_to_dict():
    """Test converting StructuredContext to dictionary."""
    context = StructuredContext(
        file_path="test.py",
        language="python",
        changes=[
            DiffChange(10, ChangeType.ADDED, "new_line = True"),
            DiffChange(11, ChangeType.REMOVED, "old_line = False")
        ]
    )
    
    result = context.to_dict()
    
    assert result["file_path"] == "test.py"
    assert result["language"] == "python"
    assert result["total_changes"] == 2
    assert result["added_lines"] == 1
    assert result["removed_lines"] == 1


def test_parse_diff_to_structured():
    """Test parsing git diff to structured context."""
    patch = """@@ -1,5 +1,6 @@
 def hello():
+    print('hello')
     pass
"""
    
    context = parse_diff_to_structured("test.py", patch)
    
    assert context.file_path == "test.py"
    assert context.language == "python"
    assert len(context.changes) > 0


def test_example_selector_builtin_examples():
    """Test that ExampleSelector provides builtin examples."""
    selector = ExampleSelector()
    
    # Should get Python examples
    examples = selector.get_examples("python", "code_review", max_examples=2)
    assert len(examples) > 0
    assert "input_code" in examples[0]
    assert "expected_output" in examples[0]
    
    # Should get JavaScript examples
    examples = selector.get_examples("javascript", "code_review", max_examples=2)
    assert len(examples) > 0


def test_example_selector_fallback():
    """Test that ExampleSelector falls back for unknown languages."""
    selector = ExampleSelector()
    
    # Unknown language should fall back to python
    examples = selector.get_examples("unknown_lang", "code_review", max_examples=2)
    assert len(examples) > 0


def test_prompt_builder_creates_structured_prompt():
    """Test that PromptBuilder creates complete structured prompts."""
    builder = PromptBuilder()
    
    context = StructuredContext(
        file_path="test.py",
        language="python",
        changes=[
            DiffChange(10, ChangeType.ADDED, "user_input = request.get('id')"),
            DiffChange(11, ChangeType.ADDED, "query = f'SELECT * FROM users WHERE id={user_input}'")
        ],
        full_content="def get_user():\n    user_input = request.get('id')\n    query = f'SELECT * FROM users WHERE id={user_input}'"
    )
    
    prompt = builder.build_review_prompt(
        context=context,
        task_type=TaskType.CODE_REVIEW,
        include_examples=True
    )
    
    # Check that prompt contains key sections
    assert "## Role" in prompt
    assert "## Instructions" in prompt
    assert "## Code Context" in prompt
    assert "## Required Output Format" in prompt
    assert "test.py" in prompt
    assert "python" in prompt.lower()


def test_prompt_builder_different_task_types():
    """Test that different task types produce different prompts."""
    builder = PromptBuilder()
    
    context = StructuredContext(
        file_path="test.py",
        language="python",
        changes=[DiffChange(10, ChangeType.ADDED, "pass")]
    )
    
    review_prompt = builder.build_review_prompt(context, TaskType.CODE_REVIEW)
    security_prompt = builder.build_review_prompt(context, TaskType.SECURITY_AUDIT)
    
    # Different task types should produce different prompts
    assert "Senior Software Engineer" in review_prompt
    assert "Security Engineer" in security_prompt


def test_prompt_builder_language_specific_instructions():
    """Test that prompts include language-specific instructions."""
    builder = PromptBuilder()
    
    python_context = StructuredContext(
        file_path="test.py",
        language="python",
        changes=[DiffChange(10, ChangeType.ADDED, "pass")]
    )
    
    js_context = StructuredContext(
        file_path="test.js",
        language="javascript",
        changes=[DiffChange(10, ChangeType.ADDED, "pass")]
    )
    
    python_prompt = builder.build_review_prompt(python_context, TaskType.CODE_REVIEW)
    js_prompt = builder.build_review_prompt(js_context, TaskType.CODE_REVIEW)
    
    # Python-specific checks
    assert "type hints" in python_prompt.lower() or "mutable default" in python_prompt.lower()
    
    # JavaScript-specific checks  
    assert "===" in js_prompt or "null" in js_prompt.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
