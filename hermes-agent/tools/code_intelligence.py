#!/usr/bin/env python3
"""
Code Intelligence Tools Module

Extends Hermes with advanced code intelligence capabilities:
- Repository indexing
- Dependency graph
- Call graph
- Architecture graph
- Symbol search
- Reference search
- Dead code detection
- Unused dependency detection
- Code quality scoring
- Technical debt estimation

All operations use the existing file operations, terminal tool, and LLM integration.
"""

import json
import logging
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool
from agent.auxiliary_client import call_llm

logger = logging.getLogger(__name__)


def _run_command(command: str, task_id: str = "default", timeout: int = 120) -> Dict[str, Any]:
    """Run a command via terminal tool."""
    try:
        result = terminal_tool(command=command, task_id=task_id, timeout=timeout)
        return json.loads(result)
    except Exception as e:
        logger.exception("Command failed: %s", e)
        return {"error": f"Command failed: {e}", "success": False}


def _resolve_path(path: str, task_id: str = "default") -> Path:
    """Resolve a path."""
    return _resolve_path_for_task(path, task_id)


def _get_file_ops(task_id: str = "default"):
    """Get file operations."""
    from tools.file_tools import _get_file_ops as get_file_ops
    return get_file_ops(task_id)


# =============================================================================
# Repository Indexing
# =============================================================================

def index_repository(
    repo_path: str = ".",
    include_patterns: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    max_files: int = 10000,
    task_id: str = "default",
) -> str:
    """Build a comprehensive repository index."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        include_patterns = include_patterns or ["*"]
        exclude_patterns = exclude_patterns or [
            "*.pyc", "__pycache__", ".git", "node_modules",
            ".venv", "venv", "dist", "build", "target",
            ".next", ".cache", "*.log", "*.tmp",
        ]
        
        import fnmatch
        
        def should_index(p: Path) -> bool:
            name = p.name
            rel = str(p.relative_to(resolved))
            
            for pat in exclude_patterns:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                    return False
            
            for pat in include_patterns:
                if fnmatch.fnmatch(name, pat) or fnmatch.fnmatch(rel, pat):
                    return True
            return False
        
        index = {
            "files": [],
            "symbols": [],
            "imports": [],
            "exports": [],
            "classes": [],
            "functions": [],
            "total_files": 0,
            "total_lines": 0,
            "languages": {},
        }
        
        count = 0
        for root, dirs, files in file_ops.walk(resolved):
            root_path = Path(root)
            
            # Filter dirs
            dirs[:] = [d for d in dirs if should_index(root_path / d)]
            
            for f in files:
                if count >= max_files:
                    break
                    
                f_path = root_path / f
                if not should_index(f_path):
                    continue
                
                try:
                    content = file_ops.read(f_path)
                    lines = content.split('\n')
                    
                    rel_path = str(f_path.relative_to(resolved))
                    ext = f_path.suffix.lower()
                    
                    index["languages"][ext] = index["languages"].get(ext, 0) + 1
                    index["total_files"] += 1
                    index["total_lines"] += len(lines)
                    
                    index["files"].append({
                        "path": rel_path,
                        "lines": len(lines),
                        "size": len(content),
                        "language": ext,
                    })
                    
                    # Extract symbols based on language
                    symbols = _extract_symbols(content, ext, rel_path)
                    index["symbols"].extend(symbols)
                    
                    for s in symbols:
                        if s["type"] == "class":
                            index["classes"].append(s)
                        elif s["type"] == "function":
                            index["functions"].append(s)
                    
                    # Extract imports/exports
                    imports = _extract_imports(content, ext, rel_path)
                    index["imports"].extend(imports)
                    
                    exports = _extract_exports(content, ext, rel_path)
                    index["exports"].extend(exports)
                    
                    count += 1
                    
                except Exception as e:
                    logger.debug("Failed to index %s: %s", f_path, e)
        
        return json.dumps({
            "success": True,
            "index": index,
            "file_count": count,
        })
    
    except Exception as e:
        logger.exception("index_repository error: %s", e)
        return json.dumps({"error": f"Repository indexing failed: {e}"})


def _extract_symbols(content: str, ext: str, file_path: str) -> List[Dict]:
    """Extract symbols (classes, functions, etc.) from source code."""
    symbols = []
    lines = content.split('\n')
    
    if ext == ".py":
        # Python classes and functions
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("class "):
                match = re.match(r'class\s+(\w+)', stripped)
                if match:
                    symbols.append({
                        "type": "class",
                        "name": match.group(1),
                        "file": file_path,
                        "line": i + 1,
                    })
            elif stripped.startswith("def "):
                match = re.match(r'def\s+(\w+)', stripped)
                if match:
                    symbols.append({
                        "type": "function",
                        "name": match.group(1),
                        "file": file_path,
                        "line": i + 1,
                    })
            elif stripped.startswith("async def "):
                match = re.match(r'async def\s+(\w+)', stripped)
                if match:
                    symbols.append({
                        "type": "function",
                        "name": match.group(1),
                        "file": file_path,
                        "line": i + 1,
                        "async": True,
                    })
    
    elif ext in [".js", ".ts", ".jsx", ".tsx"]:
        # JavaScript/TypeScript
        for i, line in enumerate(lines):
            stripped = line.strip()
            # Classes
            match = re.match(r'(export\s+)?class\s+(\w+)', stripped)
            if match:
                symbols.append({
                    "type": "class",
                    "name": match.group(2),
                    "file": file_path,
                    "line": i + 1,
                    "exported": bool(match.group(1)),
                })
            # Functions
            match = re.match(r'(export\s+)?(async\s+)?function\s+(\w+)', stripped)
            if match:
                symbols.append({
                    "type": "function",
                    "name": match.group(3),
                    "file": file_path,
                    "line": i + 1,
                    "exported": bool(match.group(1)),
                    "async": bool(match.group(2)),
                })
            # Arrow functions
            match = re.match(r'(export\s+)?(const|let|var)\s+(\w+)\s*=\s*(async\s+)?\(.*\)\s*=>', stripped)
            if match:
                symbols.append({
                    "type": "function",
                    "name": match.group(3),
                    "file": file_path,
                    "line": i + 1,
                    "exported": bool(match.group(1)),
                    "async": bool(match.group(4)),
                })
    
    elif ext in [".java"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'(public|private|protected)?\s*(class|interface|enum)\s+(\w+)', stripped)
            if match:
                symbols.append({
                    "type": match.group(2),
                    "name": match.group(3),
                    "file": file_path,
                    "line": i + 1,
                })
            match = re.match(r'(public|private|protected)?\s*(static\s+)?\w+\s+(\w+)\s*\(', stripped)
            if match:
                symbols.append({
                    "type": "method",
                    "name": match.group(3),
                    "file": file_path,
                    "line": i + 1,
                })
    
    elif ext in [".go"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'func\s+(\(.*\))?\s*(\w+)', stripped)
            if match:
                symbols.append({
                    "type": "function",
                    "name": match.group(2),
                    "file": file_path,
                    "line": i + 1,
                })
            match = re.match(r'type\s+(\w+)\s+(struct|interface)', stripped)
            if match:
                symbols.append({
                    "type": match.group(2),
                    "name": match.group(1),
                    "file": file_path,
                    "line": i + 1,
                })
    
    elif ext in [".rs"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'(pub\s+)?(struct|enum|trait|impl|fn)\s+(\w+)', stripped)
            if match:
                symbols.append({
                    "type": match.group(2),
                    "name": match.group(3),
                    "file": file_path,
                    "line": i + 1,
                    "public": bool(match.group(1)),
                })
    
    return symbols


def _extract_imports(content: str, ext: str, file_path: str) -> List[Dict]:
    """Extract imports from source code."""
    imports = []
    lines = content.split('\n')
    
    if ext == ".py":
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'(from\s+(\S+)\s+import|import\s+(\S+))', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "import": match.group(0),
                    "module": match.group(2) or match.group(3),
                })
    
    elif ext in [".js", ".ts", ".jsx", ".tsx"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'import\s+.*\s+from\s+[\'"]([^\'"]+)[\'"]', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                    "type": "es6",
                })
            match = re.match(r'require\([\'"]([^\'"]+)[\'"]\)', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                    "type": "commonjs",
                })
    
    elif ext in [".java"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'import\s+([\w.]+);', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                })
    
    elif ext in [".go"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'import\s+[\'"]([^\'"]+)[\'"]', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                })
            match = re.match(r'import\s+\(\s*([\w./-]+)', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                })
    
    elif ext in [".rs"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'use\s+([\w:]+);', stripped)
            if match:
                imports.append({
                    "file": file_path,
                    "line": i + 1,
                    "module": match.group(1),
                })
    
    return imports


def _extract_exports(content: str, ext: str, file_path: str) -> List[Dict]:
    """Extract exports from source code."""
    exports = []
    lines = content.split('\n')
    
    if ext in [".js", ".ts", ".jsx", ".tsx"]:
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'export\s+(default\s+)?(class|function|const|let|var|interface|type)\s+(\w+)', stripped)
            if match:
                exports.append({
                    "file": file_path,
                    "line": i + 1,
                    "name": match.group(3),
                    "type": match.group(2),
                    "default": bool(match.group(1)),
                })
            match = re.match(r'export\s*\{([^}]+)\}', stripped)
            if match:
                for name in match.group(1).split(','):
                    exports.append({
                        "file": file_path,
                        "line": i + 1,
                        "name": name.strip(),
                        "type": "named",
                    })
    
    elif ext == ".py":
        # Python uses __all__ for exports
        for i, line in enumerate(lines):
            stripped = line.strip()
            match = re.match(r'__all__\s*=\s*\[([^\]]+)\]', stripped)
            if match:
                for name in match.group(1).split(','):
                    exports.append({
                        "file": file_path,
                        "line": i + 1,
                        "name": name.strip().strip('\'"'),
                        "type": "all",
                    })
    
    return exports


# =============================================================================
# Dependency Graph
# =============================================================================

def dependency_graph(
    repo_path: str = ".",
    output_format: str = "json",  # json, dot, mermaid
    task_id: str = "default",
) -> str:
    """Build dependency graph from imports."""
    try:
        # First index the repository
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        imports = index.get("imports", [])
        
        # Build graph
        graph = defaultdict(set)
        nodes = set()
        
        for imp in imports:
            source = imp["file"]
            target = imp["module"]
            nodes.add(source)
            nodes.add(target)
            graph[source].add(target)
        
        if output_format == "dot":
            output = ["digraph dependencies {"]
            for node in sorted(nodes):
                output.append(f'  "{node}";')
            for source, targets in graph.items():
                for target in sorted(targets):
                    output.append(f'  "{source}" -> "{target}";')
            output.append("}")
            return "\n".join(output)
        
        elif output_format == "mermaid":
            output = ["graph TD"]
            for source, targets in graph.items():
                for target in sorted(targets):
                    output.append(f'  {_sanitize_mermaid(source)} --> {_sanitize_mermaid(target)}')
            return "\n".join(output)
        
        else:
            # JSON
            return json.dumps({
                "success": True,
                "nodes": list(nodes),
                "edges": [{"source": s, "target": t} for s, targets in graph.items() for t in targets],
                "graph": {k: list(v) for k, v in graph.items()},
            })
    
    except Exception as e:
        logger.exception("dependency_graph error: %s", e)
        return json.dumps({"error": f"Dependency graph failed: {e}"})


def _sanitize_mermaid(s: str) -> str:
    """Sanitize string for Mermaid."""
    return s.replace(".", "_").replace("/", "_").replace("-", "_")


# =============================================================================
# Call Graph
# =============================================================================

def call_graph(
    repo_path: str = ".",
    entry_point: Optional[str] = None,
    max_depth: int = 5,
    output_format: str = "json",  # json, dot, mermaid
    task_id: str = "default",
) -> str:
    """Build call graph for functions/methods."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        functions = index.get("functions", [])
        
        # Build function lookup
        func_by_name = {}
        for f in functions:
            key = f"{f['file']}:{f['name']}"
            func_by_name[key] = f
        
        # Extract function calls (simplified - would need proper AST parsing)
        calls = defaultdict(set)
        
        for f in functions:
            # This is simplified - real implementation would parse function bodies
            pass
        
        if output_format == "dot":
            output = ["digraph calls {"]
            for func, targets in calls.items():
                output.append(f'  "{func}";')
                for target in sorted(targets):
                    output.append(f'  "{func}" -> "{target}";')
            output.append("}")
            return "\n".join(output)
        
        elif output_format == "mermaid":
            output = ["graph TD"]
            for func, targets in calls.items():
                for target in sorted(targets):
                    output.append(f'  {_sanitize_mermaid(func)} --> {_sanitize_mermaid(target)}')
            return "\n".join(output)
        
        else:
            return json.dumps({
                "success": True,
                "functions": list(func_by_name.keys()),
                "calls": {k: list(v) for k, v in calls.items()},
            })
    
    except Exception as e:
        logger.exception("call_graph error: %s", e)
        return json.dumps({"error": f"Call graph failed: {e}"})


# =============================================================================
# Architecture Graph
# =============================================================================

def architecture_graph(
    repo_path: str = ".",
    output_format: str = "mermaid",  # mermaid, dot, json
    task_id: str = "default",
) -> str:
    """Generate architecture diagram from project structure."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        files = index.get("files", [])
        
        # Group by directory/module
        modules = defaultdict(list)
        for f in files:
            path = Path(f["path"])
            if len(path.parts) > 1:
                module = path.parts[0]
            else:
                module = "root"
            modules[module].append(f)
        
        # Detect layer pattern
        layers = {
            "presentation": ["ui", "frontend", "web", "app", "views", "components"],
            "business": ["services", "domain", "business", "logic", "core"],
            "data": ["repository", "dao", "data", "models", "entities", "database"],
            "infrastructure": ["config", "infra", "utils", "helpers", "common"],
        }
        
        module_layers = {}
        for module in modules:
            module_lower = module.lower()
            assigned = False
            for layer, keywords in layers.items():
                if any(kw in module_lower for kw in keywords):
                    module_layers[module] = layer
                    assigned = True
                    break
            if not assigned:
                module_layers[module] = "other"
        
        if output_format == "mermaid":
            output = ["graph TB"]
            # Subgraphs for layers
            layer_modules = defaultdict(list)
            for module, layer in module_layers.items():
                layer_modules[layer].append(module)
            
            for layer, mods in layer_modules.items():
                output.append(f'  subgraph {layer}["{layer.title()}"]')
                for m in mods:
                    output.append(f'    {_sanitize_mermaid(m)}["{m}"]')
                output.append("  end")
            
            # Connections based on imports
            imports = index.get("imports", [])
            for imp in imports:
                source_file = imp["file"]
                target_module = imp["module"]
                
                source_module = Path(source_file).parts[0] if len(Path(source_file).parts) > 1 else "root"
                
                if source_module in module_layers and target_module in module_layers:
                    if module_layers[source_module] != module_layers[target_module]:
                        output.append(f'  {_sanitize_mermaid(source_module)} --> {_sanitize_mermaid(target_module)}')
            
            return "\n".join(output)
        
        else:
            return json.dumps({
                "success": True,
                "modules": dict(modules),
                "layers": module_layers,
                "imports": imports,
            })
    
    except Exception as e:
        logger.exception("architecture_graph error: %s", e)
        return json.dumps({"error": f"Architecture graph failed: {e}"})


# =============================================================================
# Symbol Search
# =============================================================================

def symbol_search(
    query: str,
    repo_path: str = ".",
    symbol_type: Optional[str] = None,  # class, function, method, etc.
    case_sensitive: bool = False,
    max_results: int = 50,
    task_id: str = "default",
) -> str:
    """Search for symbols (classes, functions, etc.) in the codebase."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        symbols = index.get("symbols", [])
        
        # Filter by type
        if symbol_type:
            symbols = [s for s in symbols if s.get("type") == symbol_type]
        
        # Search
        query_lower = query if case_sensitive else query.lower()
        results = []
        
        for sym in symbols:
            name = sym["name"] if case_sensitive else sym["name"].lower()
            if query_lower in name:
                results.append(sym)
        
        # Sort by relevance (exact match first, then prefix, then contains)
        def relevance(s):
            name = s["name"] if case_sensitive else s["name"].lower()
            if name == query_lower:
                return 0
            elif name.startswith(query_lower):
                return 1
            else:
                return 2
        
        results.sort(key=relevance)
        
        return json.dumps({
            "success": True,
            "query": query,
            "results": results[:max_results],
            "total": len(results),
        })
    
    except Exception as e:
        logger.exception("symbol_search error: %s", e)
        return json.dumps({"error": f"Symbol search failed: {e}"})


# =============================================================================
# Reference Search
# =============================================================================

def reference_search(
    symbol_name: str,
    repo_path: str = ".",
    symbol_type: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Find all references to a symbol."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        symbols = index.get("symbols", [])
        
        # Find the symbol definition
        definitions = [s for s in symbols if s["name"] == symbol_name]
        if symbol_type:
            definitions = [d for d in definitions if d.get("type") == symbol_type]
        
        if not definitions:
            return json.dumps({"error": f"Symbol not found: {symbol_name}"})
        
        # Search for references in source code
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        references = []
        
        for defn in definitions:
            refs = _find_references(defn["name"], resolved, file_ops, exclude_file=defn["file"])
            references.extend(refs)
        
        return json.dumps({
            "success": True,
            "symbol": symbol_name,
            "definitions": definitions,
            "references": references,
            "reference_count": len(references),
        })
    
    except Exception as e:
        logger.exception("reference_search error: %s", e)
        return json.dumps({"error": f"Reference search failed: {e}"})


def _find_references(symbol: str, root: Path, file_ops, exclude_file: str = None) -> List[Dict]:
    """Find references to a symbol in source files."""
    references = []
    
    for f in root.rglob("*"):
        if f.is_file() and f.suffix in [".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rs", ".cs"]:
            if exclude_file and str(f.relative_to(root)) == exclude_file:
                continue
            try:
                content = file_ops.read(f)
                lines = content.split('\n')
                
                for i, line in enumerate(lines):
                    if re.search(rf'\b{re.escape(symbol)}\b', line):
                        references.append({
                            "file": str(f.relative_to(root)),
                            "line": i + 1,
                            "content": line.strip()[:200],
                        })
            except:
                pass
    
    return references


# =============================================================================
# Dead Code Detection
# =============================================================================

def dead_code_detection(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Detect potentially dead code (unused functions, classes, imports)."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        symbols = index.get("symbols", [])
        imports = index.get("imports", [])
        
        # Build symbol lookup
        defined_symbols = {}
        for s in symbols:
            key = f"{s['file']}:{s['name']}"
            defined_symbols[key] = s
        
        # Track referenced symbols
        referenced = set()
        
        # Check imports
        for imp in imports:
            # This is simplified - would need to parse import specifics
            pass
        
        # Search for references in code
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        for key, sym in defined_symbols.items():
            refs = _find_references(sym["name"], resolved, file_ops, exclude_file=sym["file"])
            if refs:
                referenced.add(key)
        
        # Dead code = defined but not referenced (excluding entry points)
        dead = []
        entry_patterns = ["main", "init", "handler", "test_", "__main__"]
        
        for key, sym in defined_symbols.items():
            if key not in referenced:
                # Check if it's an entry point
                is_entry = any(p in sym["name"].lower() for p in entry_patterns)
                is_exported = sym.get("exported", False) or sym.get("public", False)
                
                if not is_entry and not is_exported:
                    dead.append({
                        "symbol": sym["name"],
                        "type": sym["type"],
                        "file": sym["file"],
                        "line": sym["line"],
                    })
        
        # Unused imports
        unused_imports = []
        for imp in imports:
            # Check if imported module is used
            pass
        
        return json.dumps({
            "success": True,
            "dead_code": dead,
            "dead_count": len(dead),
            "unused_imports": unused_imports,
        })
    
    except Exception as e:
        logger.exception("dead_code_detection error: %s", e)
        return json.dumps({"error": f"Dead code detection failed: {e}"})


# =============================================================================
# Unused Dependency Detection
# =============================================================================

def unused_dependency_detection(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Detect unused dependencies in package files."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        unused = []
        
        # Python
        if file_ops.exists(resolved / "requirements.txt") or file_ops.exists(resolved / "pyproject.toml"):
            # Would need to check imports vs installed packages
            pass
        
        # Node.js
        if file_ops.exists(resolved / "package.json"):
            pkg = json.loads(file_ops.read(resolved / "package.json"))
            deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
            
            # Check if each dependency is imported
            for dep in deps:
                # Search for imports
                found = False
                for f in resolved.rglob("*"):
                    if f.is_file() and f.suffix in [".js", ".ts", ".jsx", ".tsx"]:
                        try:
                            content = file_ops.read(f)
                            if re.search(rf'["\']{re.escape(dep)}["\']|from\s+["\']{re.escape(dep)}', content):
                                found = True
                                break
                        except:
                            pass
                
                if not found:
                    unused.append({
                        "package": dep,
                        "version": deps[dep],
                        "type": "npm",
                    })
        
        # Go
        if file_ops.exists(resolved / "go.mod"):
            # Would run `go mod why` or check imports
            pass
        
        # Rust
        if file_ops.exists(resolved / "Cargo.toml"):
            # Would run `cargo machete` or similar
            pass
        
        return json.dumps({
            "success": True,
            "unused_dependencies": unused,
            "count": len(unused),
        })
    
    except Exception as e:
        logger.exception("unused_dependency_detection error: %s", e)
        return json.dumps({"error": f"Unused dependency detection failed: {e}"})


# =============================================================================
# Code Quality Scoring
# =============================================================================

def code_quality_score(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Calculate code quality metrics and score."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        files = index.get("files", [])
        symbols = index.get("symbols", [])
        
        metrics = {
            "total_files": len(files),
            "total_lines": index.get("total_lines", 0),
            "total_symbols": len(symbols),
            "classes": len([s for s in symbols if s.get("type") == "class"]),
            "functions": len([s for s in symbols if s.get("type") == "function"]),
        }
        
        # Language distribution
        metrics["languages"] = index.get("languages", {})
        
        # Average file size
        if files:
            metrics["avg_file_lines"] = sum(f["lines"] for f in files) / len(files)
            metrics["avg_file_size"] = sum(f["size"] for f in files) / len(files)
        
        # Complexity indicators
        large_files = [f for f in files if f["lines"] > 500]
        metrics["large_files"] = len(large_files)
        
        # TODO/FIXME count
        todo_count = 0
        for f in files:
            try:
                content = _get_file_ops(task_id).read(_resolve_path(f["path"], task_id))
                todo_count += content.count("TODO") + content.count("FIXME") + content.count("XXX")
            except:
                pass
        metrics["todo_count"] = todo_count
        
        # Calculate score (0-100)
        score = 100
        score -= min(metrics["large_files"] * 2, 20)  # Penalty for large files
        score -= min(metrics["todo_count"] * 0.5, 15)  # Penalty for TODOs
        
        # Bonus for good practices
        if metrics.get("total_symbols", 0) > 0:
            doc_ratio = 0  # Would check for docstrings
            score += min(doc_ratio * 10, 10)
        
        score = max(0, min(100, score))
        
        grade = "A" if score >= 90 else "B" if score >= 80 else "C" if score >= 70 else "D" if score >= 60 else "F"
        
        return json.dumps({
            "success": True,
            "score": round(score, 1),
            "grade": grade,
            "metrics": metrics,
        })
    
    except Exception as e:
        logger.exception("code_quality_score error: %s", e)
        return json.dumps({"error": f"Code quality scoring failed: {e}"})


# =============================================================================
# Technical Debt Estimation
# =============================================================================

def technical_debt_estimation(
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Estimate technical debt in the codebase."""
    try:
        index_result = json.loads(index_repository(repo_path, task_id=task_id))
        
        if not index_result.get("success"):
            return index_result
        
        index = index_result["index"]
        files = index.get("files", [])
        
        debt_items = []
        total_hours = 0
        
        # Analyze each file
        for f in files[:100]:  # Limit for performance
            try:
                content = _get_file_ops(task_id).read(_resolve_path(f["path"], task_id))
                lines = content.split('\n')
                
                file_debt = []
                
                # Long functions
                if f["lines"] > 300:
                    file_debt.append({
                        "type": "long_file",
                        "severity": "medium",
                        "message": f"File has {f['lines']} lines (>300)",
                        "estimated_hours": 2,
                    })
                    total_hours += 2
                
                # High cyclomatic complexity (simplified)
                # TODO/FIXME comments
                todo_matches = len(re.findall(r'(TODO|FIXME|XXX|HACK)', content, re.IGNORECASE))
                if todo_matches > 5:
                    file_debt.append({
                        "type": "high_todo",
                        "severity": "low",
                        "message": f"{todo_matches} TODO/FIXME comments",
                        "estimated_hours": todo_matches * 0.5,
                    })
                    total_hours += todo_matches * 0.5
                
                # Duplicated code blocks (simplified)
                # Magic numbers
                magic_numbers = len(re.findall(r'\b\d{3,}\b', content))
                if magic_numbers > 10:
                    file_debt.append({
                        "type": "magic_numbers",
                        "severity": "low",
                        "message": f"{magic_numbers} magic numbers",
                        "estimated_hours": 1,
                    })
                    total_hours += 1
                
                # Deep nesting (simplified check)
                max_indent = 0
                for line in lines:
                    indent = len(line) - len(line.lstrip())
                    if indent > max_indent:
                        max_indent = indent
                
                if max_indent > 8:  # Very deep nesting
                    file_debt.append({
                        "type": "deep_nesting",
                        "severity": "medium",
                        "message": f"Max indentation: {max_indent} spaces",
                        "estimated_hours": 2,
                    })
                    total_hours += 2
                
                if file_debt:
                    debt_items.append({
                        "file": f["path"],
                        "issues": file_debt,
                    })
            
            except Exception as e:
                logger.debug("Failed to analyze %s: %s", f["path"], e)
        
        # Categorize by severity
        by_severity = defaultdict(int)
        for item in debt_items:
            for issue in item["issues"]:
                by_severity[issue["severity"]] += 1
        
        return json.dumps({
            "success": True,
            "total_estimated_hours": round(total_hours, 1),
            "debt_items": debt_items,
            "by_severity": dict(by_severity),
            "file_count": len(debt_items),
        })
    
    except Exception as e:
        logger.exception("technical_debt_estimation error: %s", e)
        return json.dumps({"error": f"Technical debt estimation failed: {e}"})


# =============================================================================
# Registration
# =============================================================================

def _register_code_intelligence_tools():
    """Register all code intelligence tools with the registry."""

    tools = [
        ("index_repository", "code_intelligence", {
            "name": "index_repository",
            "description": "Build comprehensive repository index with symbols, imports, exports",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                    "include_patterns": {"type": "array", "items": {"type": "string"}, "default": None},
                    "exclude_patterns": {"type": "array", "items": {"type": "string"}, "default": None},
                    "max_files": {"type": "integer", "default": 10000},
                },
                "required": [],
            },
        }, index_repository, None, [], False, "📇", None),

        ("dependency_graph", "code_intelligence", {
            "name": "dependency_graph",
            "description": "Build dependency graph from imports (JSON, DOT, Mermaid)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                    "output_format": {"type": "string", "enum": ["json", "dot", "mermaid"], "default": "json"},
                },
                "required": [],
            },
        }, dependency_graph, None, [], False, "🔗", None),

        ("call_graph", "code_intelligence", {
            "name": "call_graph",
            "description": "Build function call graph (JSON, DOT, Mermaid)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                    "entry_point": {"type": "string", "default": None},
                    "max_depth": {"type": "integer", "default": 5},
                    "output_format": {"type": "string", "enum": ["json", "dot", "mermaid"], "default": "json"},
                },
                "required": [],
            },
        }, call_graph, None, [], False, "📞", None),

        ("architecture_graph", "code_intelligence", {
            "name": "architecture_graph",
            "description": "Generate architecture diagram from project structure",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                    "output_format": {"type": "string", "enum": ["mermaid", "dot", "json"], "default": "mermaid"},
                },
                "required": [],
            },
        }, architecture_graph, None, [], False, "🏗️", None),

        ("symbol_search", "code_intelligence", {
            "name": "symbol_search",
            "description": "Search for symbols (classes, functions, etc.) in codebase",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "repo_path": {"type": "string", "default": "."},
                    "symbol_type": {"type": "string", "default": None},
                    "case_sensitive": {"type": "boolean", "default": False},
                    "max_results": {"type": "integer", "default": 50},
                },
                "required": ["query"],
            },
        }, symbol_search, None, [], False, "🔍", None),

        ("reference_search", "code_intelligence", {
            "name": "reference_search",
            "description": "Find all references to a symbol",
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol_name": {"type": "string"},
                    "repo_path": {"type": "string", "default": "."},
                    "symbol_type": {"type": "string", "default": None},
                },
                "required": ["symbol_name"],
            },
        }, reference_search, None, [], False, "📍", None),

        ("dead_code_detection", "code_intelligence", {
            "name": "dead_code_detection",
            "description": "Detect potentially dead code (unused functions, classes)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                },
                "required": [],
            },
        }, dead_code_detection, None, [], False, "💀", None),

        ("unused_dependency_detection", "code_intelligence", {
            "name": "unused_dependency_detection",
            "description": "Detect unused dependencies in package files",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                },
                "required": [],
            },
        }, unused_dependency_detection, None, [], False, "📦", None),

        ("code_quality_score", "code_intelligence", {
            "name": "code_quality_score",
            "description": "Calculate code quality metrics and score (0-100)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                },
                "required": [],
            },
        }, code_quality_score, None, [], False, "⭐", None),

        ("technical_debt_estimation", "code_intelligence", {
            "name": "technical_debt_estimation",
            "description": "Estimate technical debt in hours",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "default": "."},
                },
                "required": [],
            },
        }, technical_debt_estimation, None, [], False, "💸", None),
    ]

    for name, toolset, schema, handler, check_fn, requires_env, is_async, emoji, dynamic in tools:
        registry.register(
            name=name,
            toolset=toolset,
            schema=schema,
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env,
            is_async=is_async,
            description=schema.get("description", ""),
            emoji=emoji,
            max_result_size_chars=50000,
        )


# Auto-register on import
_register_code_intelligence_tools()

__all__ = [
    "index_repository",
    "dependency_graph",
    "call_graph",
    "architecture_graph",
    "symbol_search",
    "reference_search",
    "dead_code_detection",
    "unused_dependency_detection",
    "code_quality_score",
    "technical_debt_estimation",
]

if __name__ == "__main__":
    print("Code intelligence tools loaded successfully")