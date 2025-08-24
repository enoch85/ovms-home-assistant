#!/usr/bin/env python3
"""
OVMS Home Assistant Integration - Code Quality Test Suite

This script validates the codebase following Python and Home Assistant best practices.
All tests should pass (green) for a release-ready integration.
"""

import ast
import importlib.util
import sys
import py_compile
from pathlib import Path
from typing import Dict, List, Tuple, Optional, Set
from dataclasses import dataclass
import re


@dataclass
class TestResult:
    """Container for test results."""
    passed: bool
    message: str
    warnings: List[str] = None
    
    def __post_init__(self):
        if self.warnings is None:
            self.warnings = []


class Colors:
    """ANSI color codes for terminal output."""
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    END = '\033[0m'


def print_colored(text: str, color: str) -> None:
    """Print colored text to terminal."""
    print(f"{color}{text}{Colors.END}")


def print_success(text: str) -> None:
    """Print success message in green."""
    print_colored(f"✅ {text}", Colors.GREEN)


def print_error(text: str) -> None:
    """Print error message in red."""
    print_colored(f"❌ {text}", Colors.RED)


def print_warning(text: str) -> None:
    """Print warning message in yellow."""
    print_colored(f"⚠️  {text}", Colors.YELLOW)


def print_info(text: str) -> None:
    """Print info message in blue."""
    print_colored(f"ℹ️  {text}", Colors.BLUE)


class CodeQualityValidator:
    """Validates code quality following Python and Home Assistant best practices."""
    
    def __init__(self, base_path: Path):
        self.base_path = base_path
        self.custom_components_path = base_path / "custom_components" / "ovms"
        
        # Home Assistant framework imports that are expected to be missing in dev environment
        self.ha_framework_imports = {
            'homeassistant', 'voluptuous', 'aiohttp', 'paho.mqtt',
            'aio_mqtt', 'asyncio_mqtt', 'pycryptodome', 'aiomqtt'
        }
        
        # Known Home Assistant platform modules
        self.ha_platform_modules = {
            'sensor', 'binary_sensor', 'device_tracker', 'switch', 'config_flow'
        }
    
    def find_python_files(self) -> List[Path]:
        """Find all Python files in the custom components directory."""
        python_files = []
        
        if self.custom_components_path.exists():
            for file_path in self.custom_components_path.rglob("*.py"):
                # Skip __pycache__ directories
                if "__pycache__" not in str(file_path):
                    python_files.append(file_path)
        
        return sorted(python_files)
    
    def test_syntax(self, file_path: Path) -> TestResult:
        """Test if a Python file has valid syntax."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                source = f.read()
            
            ast.parse(source, filename=str(file_path))
            return TestResult(True, "Syntax check passed")
            
        except SyntaxError as e:
            return TestResult(False, f"Syntax error: {e}")
        except Exception as e:
            return TestResult(False, f"Error reading file: {e}")
    
    def test_compilation(self, file_path: Path) -> TestResult:
        """Test if a Python file can be compiled."""
        try:
            py_compile.compile(str(file_path), doraise=True)
            return TestResult(True, "Compilation passed")
        except py_compile.PyCompileError as e:
            return TestResult(False, f"Compilation failed: {e}")
        except Exception as e:
            return TestResult(False, f"Compilation error: {e}")
    
    def test_imports(self, file_path: Path) -> TestResult:
        """Test imports following Home Assistant best practices."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(file_path))
            issues = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        result = self._validate_import(alias.name, file_path)
                        if result:
                            issues.append(result)
                
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        result = self._validate_from_import(node.module, file_path)
                        if result:
                            issues.append(result)
            
            if issues:
                return TestResult(False, "Import validation failed", issues)
            
            return TestResult(True, "Import check passed")
            
        except Exception as e:
            return TestResult(False, f"Error checking imports: {e}")
    
    def _validate_import(self, module_name: str, file_path: Path) -> Optional[str]:
        """Validate a regular import statement."""
        # Skip known framework imports
        if any(framework in module_name.lower() for framework in self.ha_framework_imports):
            return None
        
        try:
            __import__(module_name)
            return None
        except ImportError:
            # Only report critical import errors for our own modules
            if module_name.startswith('custom_components'):
                return f"Cannot import module '{module_name}'"
            return None
    
    def _validate_from_import(self, module_name: str, file_path: Path) -> Optional[str]:
        """Validate a 'from ... import ...' statement."""
        # Skip relative imports (they start with .)
        if module_name.startswith('.'):
            return None
        
        # Skip known framework imports
        if any(framework in module_name.lower() for framework in self.ha_framework_imports):
            return None
        
        # Skip re-exports and circular imports within the same package
        file_name = file_path.name
        if (file_name == 'config_flow.py' and module_name == 'config_flow') or \
           (file_name == 'sensor.py' and module_name == 'sensor') or \
           (file_name == '__init__.py' and module_name in self.ha_platform_modules):
            return None
        
        try:
            __import__(module_name)
            return None
        except ImportError:
            # Only report critical import errors for our own modules
            if module_name.startswith('custom_components'):
                return f"Cannot import from module '{module_name}'"
            return None
    
    def test_async_patterns(self, file_path: Path) -> TestResult:
        """Test async/await patterns following Home Assistant best practices."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            tree = ast.parse(content, filename=str(file_path))
            issues = []
            
            # Find all function definitions and check async patterns
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    # Skip properties, they cannot be async
                    if any(isinstance(decorator, ast.Name) and decorator.id == 'property' 
                           for decorator in node.decorator_list):
                        continue
                    
                    # Check if function uses await but is not async
                    has_await = self._has_await_in_function(node)
                    is_async = isinstance(node, ast.AsyncFunctionDef)
                    
                    if has_await and not is_async:
                        issues.append(f"Line {node.lineno}: Function '{node.name}' uses 'await' but is not declared as 'async'")
            
            if issues:
                return TestResult(False, "Async pattern validation failed", issues)
            
            return TestResult(True, "Async patterns check passed")
            
        except Exception as e:
            return TestResult(False, f"Error checking async patterns: {e}")
    
    def _has_await_in_function(self, func_node: ast.FunctionDef) -> bool:
        """Check if a function contains await expressions."""
        for node in ast.walk(func_node):
            if isinstance(node, ast.Await):
                return True
        return False
    
    def test_home_assistant_patterns(self, file_path: Path) -> TestResult:
        """Test Home Assistant specific patterns and best practices."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            warnings = []
            lines = content.split('\n')
            
            for i, line in enumerate(lines, 1):
                line_stripped = line.strip()
                
                # Check for deprecated imports
                if 'homeassistant.const import STATE_' in line:
                    warnings.append(f"Line {i}: Deprecated STATE_ import, use string literals instead")
                
                # Check for old-style platform setup
                if 'def setup_platform(' in line:
                    warnings.append(f"Line {i}: Old-style platform setup, use async_setup_entry instead")
                
                # Check for missing type hints in public methods
                if (line_stripped.startswith('def ') and 
                    not line_stripped.startswith('def _') and  # Skip private methods
                    '->' not in line and
                    '__init__' not in line):
                    warnings.append(f"Line {i}: Consider adding return type annotation")
            
            return TestResult(True, "Home Assistant patterns check passed", warnings)
            
        except Exception as e:
            return TestResult(False, f"Error checking HA patterns: {e}")
    
    def test_file_structure(self) -> TestResult:
        """Test file structure requirements for Home Assistant components."""
        issues = []
        
        # Check for required __init__.py files
        required_init_dirs = [
            self.custom_components_path,
            self.custom_components_path / "config_flow",
            self.custom_components_path / "metrics",
            self.custom_components_path / "metrics" / "common",
            self.custom_components_path / "metrics" / "vehicles",
            self.custom_components_path / "mqtt",
            self.custom_components_path / "sensor",
            self.custom_components_path / "translations",
        ]
        
        for dir_path in required_init_dirs:
            if dir_path.exists():
                init_file = dir_path / "__init__.py"
                if not init_file.exists():
                    issues.append(f"Missing __init__.py in {dir_path.relative_to(self.base_path)}")
        
        # Check for required files
        required_files = [
            self.custom_components_path / "manifest.json",
            self.custom_components_path / "const.py",
        ]
        
        for file_path in required_files:
            if not file_path.exists():
                issues.append(f"Missing required file: {file_path.relative_to(self.base_path)}")
        
        if issues:
            return TestResult(False, "File structure validation failed", issues)
        
        return TestResult(True, "File structure check passed")


def main():
    """Run the complete test suite."""
    print_colored("🧪 OVMS Home Assistant Integration - Code Quality Test Suite", Colors.BOLD + Colors.CYAN)
    print_colored("=" * 80, Colors.CYAN)
    
    base_path = Path(__file__).parent.parent.parent  # Go up to workspace root
    validator = CodeQualityValidator(base_path)
    
    # Find all Python files
    python_files = validator.find_python_files()
    print_info(f"Found {len(python_files)} Python files to test")
    print()
    
    # Test counters
    total_files = len(python_files)
    syntax_errors = 0
    compilation_errors = 0
    import_errors = 0
    async_errors = 0
    total_warnings = 0
    
    # Run tests for each file
    print_colored("📋 Running Code Quality Tests:", Colors.WHITE)
    print_colored("-" * 40, Colors.CYAN)
    
    for file_path in python_files:
        rel_path = file_path.relative_to(base_path)
        print_colored(f"\n🔍 Testing: {rel_path}", Colors.BLUE)
        
        # Test syntax
        result = validator.test_syntax(file_path)
        if result.passed:
            print_success("  Syntax check passed")
        else:
            print_error(f"  {result.message}")
            syntax_errors += 1
            continue  # Skip other tests if syntax is broken
        
        # Test compilation
        result = validator.test_compilation(file_path)
        if result.passed:
            print_success("  Compilation passed")
        else:
            print_error(f"  {result.message}")
            compilation_errors += 1
        
        # Test imports
        result = validator.test_imports(file_path)
        if result.passed:
            print_success("  Import validation passed")
        else:
            print_error(f"  {result.message}")
            for issue in result.warnings:
                print_error(f"    {issue}")
            import_errors += 1
        
        # Test async patterns
        result = validator.test_async_patterns(file_path)
        if result.passed:
            print_success("  Async patterns check passed")
        else:
            print_error(f"  {result.message}")
            for issue in result.warnings:
                print_error(f"    {issue}")
            async_errors += 1
        
        # Test Home Assistant patterns (warnings only)
        result = validator.test_home_assistant_patterns(file_path)
        if result.warnings:
            for warning in result.warnings:
                print_warning(f"  {warning}")
                total_warnings += 1
    
    # Test file structure
    print_colored("\n📁 Testing File Structure:", Colors.WHITE)
    print_colored("-" * 40, Colors.CYAN)
    
    result = validator.test_file_structure()
    if result.passed:
        print_success("File structure validation passed")
    else:
        print_error(result.message)
        for issue in result.warnings:
            print_error(f"  {issue}")
    
    # Summary
    print_colored("\n📊 Test Summary:", Colors.WHITE)
    print_colored("=" * 60, Colors.CYAN)
    
    print_colored(f"Total files tested: {total_files}", Colors.WHITE)
    
    if syntax_errors == 0:
        print_success(f"Syntax errors: {syntax_errors}")
    else:
        print_error(f"Syntax errors: {syntax_errors}")
    
    if compilation_errors == 0:
        print_success(f"Compilation errors: {compilation_errors}")
    else:
        print_error(f"Compilation errors: {compilation_errors}")
    
    if import_errors == 0:
        print_success(f"Import errors: {import_errors}")
    else:
        print_error(f"Import errors: {import_errors}")
    
    if async_errors == 0:
        print_success(f"Async pattern errors: {async_errors}")
    else:
        print_error(f"Async pattern errors: {async_errors}")
    
    if total_warnings == 0:
        print_success(f"Warnings: {total_warnings}")
    else:
        print_warning(f"Warnings: {total_warnings}")
    
    total_errors = syntax_errors + compilation_errors + import_errors + async_errors
    
    print_colored(f"\n🎯 Overall Result:", Colors.WHITE)
    
    if total_errors == 0:
        print_success("✨ All tests passed! Integration is ready for release.")
        return 0
    else:
        print_error(f"❌ {total_errors} critical issues found. Please fix before releasing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
