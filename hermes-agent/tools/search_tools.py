#!/usr/bin/env python3
"""
Enhanced Search Tools Module

Provides advanced search capabilities:
- Semantic/vector search
- Workspace-wide search
- Regex search
- Dependency search
- Documentation search
"""

import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Try to import optional dependencies
try:
    import chromadb
    from chromadb.utils import embedding_functions
    CHROMA_AVAILABLE = True
except ImportError:
    CHROMA_AVAILABLE = False

try:
    import sentence_transformers
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False


# Global vector store
_vector_store = None
_vector_store_lock = threading.Lock()


def _get_vector_store(persist_dir: Optional[str] = None):
    """Get or create vector store."""
    global _vector_store
    
    if not CHROMA_AVAILABLE:
        return None
    
    with _vector_store_lock:
        if _vector_store is None:
            if persist_dir is None:
                persist_dir = str(Path.home() / ".hermes" / "vector_store")
            
            client = chromadb.PersistentClient(path=persist_dir)
            
            # Use sentence transformers for embeddings
            if SENTENCE_TRANSFORMERS_AVAILABLE:
                ef = embedding_functions.SentenceTransformerEmbeddingFunction(
                    model_name="all-MiniLM-L6-v2"
                )
            else:
                ef = embedding_functions.DefaultEmbeddingFunction()
            
            _vector_store = client.get_or_create_collection(
                name="workspace",
                embedding_function=ef,
            )
        
        return _vector_store


def semantic_search(
    query: str,
    path: str = ".",
    top_k: int = 10,
    filter_metadata: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Semantic/vector search across workspace.
    
    Args:
        query: Search query
        path: Path to search (used for metadata filtering)
        top_k: Number of results
        filter_metadata: Metadata filters
        task_id: Task identifier
        
    Returns:
        JSON string with search results
    """
    if not CHROMA_AVAILABLE:
        return json.dumps({
            "error": "ChromaDB not installed. Run: pip install chromadb sentence-transformers"
        })
    
    try:
        vector_store = _get_vector_store()
        if not vector_store:
            return json.dumps({"error": "Failed to initialize vector store"})
        
        # Build where clause
        where = {}
        if filter_metadata:
            where.update(filter_metadata)
        
        # Resolve path for metadata
        resolved = _resolve_path(path, task_id)
        if resolved:
            where["path"] = {"$regex": f"^{re.escape(str(resolved))}"}
        
        results = vector_store.query(
            query_texts=[query],
            n_results=top_k,
            where=where if where else None,
            include=["documents", "metadatas", "distances"],
        )
        
        formatted = []
        for i in range(len(results["documents"][0])):
            formatted.append({
                "content": results["documents"][0][i],
                "metadata": results["metadatas"][0][i],
                "distance": results["distances"][0][i],
            })
        
        return json.dumps({"success": True, "results": formatted})
        
    except Exception as e:
        logger.exception("Semantic search failed")
        return json.dumps({"error": str(e)})


def index_workspace(
    path: str = ".",
    extensions: Optional[List[str]] = None,
    exclude_patterns: Optional[List[str]] = None,
    chunk_size: int = 1000,
    chunk_overlap: int = 200,
    task_id: str = "default",
) -> str:
    """Index workspace for semantic search.
    
    Args:
        path: Root path to index
        extensions: File extensions to include
        exclude_patterns: Patterns to exclude
        chunk_size: Chunk size for large files
        chunk_overlap: Overlap between chunks
        task_id: Task identifier
        
    Returns:
        JSON string with indexing result
    """
    if not CHROMA_AVAILABLE:
        return json.dumps({
            "error": "ChromaDB not installed. Run: pip install chromadb sentence-transformers"
        })
    
    try:
        vector_store = _get_vector_store()
        if not vector_store:
            return json.dumps({"error": "Failed to initialize vector store"})
        
        resolved = _resolve_path(path, task_id)
        if not resolved or not resolved.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        
        # Default extensions
        if extensions is None:
            extensions = [
                ".py", ".js", ".ts", ".tsx", ".jsx", ".md", ".txt", ".rst",
                ".json", ".yaml", ".yml", ".toml", ".ini", ".cfg",
                ".go", ".rs", ".java", ".kt", ".swift", ".cpp", ".c", ".h",
                ".cs", ".php", ".rb", ".pl", ".sh", ".bash", ".zsh",
                ".sql", ".graphql", ".proto", ".dockerfile", ".tf",
            ]
        
        # Default exclude patterns
        if exclude_patterns is None:
            exclude_patterns = [
                "**/node_modules/**", "**/.git/**", "**/__pycache__/**",
                "**/dist/**", "**/build/**", "**/.venv/**", "**/venv/**",
                "**/target/**", "**/*.min.js", "**/*.map",
            ]
        
        files_indexed = 0
        chunks_indexed = 0
        
        # Collect files
        file_paths = []
        for ext in extensions:
            file_paths.extend(resolved.rglob(f"*{ext}"))
        
        # Filter excluded
        filtered = []
        for f in file_paths:
            rel = f.relative_to(resolved)
            if not any(rel.match(p) for p in exclude_patterns):
                filtered.append(f)
        
        # Index files
        for file_path in filtered:
            try:
                content = file_path.read_text(encoding="utf-8", errors="ignore")
                if not content.strip():
                    continue
                
                # Chunk content
                chunks = _chunk_text(content, chunk_size, chunk_overlap)
                
                for i, chunk in enumerate(chunks):
                    if len(chunk.strip()) < 50:
                        continue
                    
                    doc_id = f"{file_path.relative_to(resolved)}#{i}"
                    metadata = {
                        "path": str(file_path.relative_to(resolved)),
                        "file": file_path.name,
                        "extension": file_path.suffix,
                        "chunk": i,
                        "total_chunks": len(chunks),
                    }
                    
                    vector_store.add(
                        documents=[chunk],
                        metadatas=[metadata],
                        ids=[doc_id],
                    )
                    chunks_indexed += 1
                
                files_indexed += 1
                
            except Exception as e:
                logger.warning(f"Failed to index {file_path}: {e}")
        
        return json.dumps({
            "success": True,
            "files_indexed": files_indexed,
            "chunks_indexed": chunks_indexed,
        })
        
    except Exception as e:
        logger.exception("Workspace indexing failed")
        return json.dumps({"error": str(e)})


def _chunk_text(text: str, chunk_size: int, overlap: int) -> List[str]:
    """Split text into overlapping chunks."""
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunk = text[start:end]
        
        # Try to break at sentence/paragraph boundary
        if end < len(text):
            last_period = chunk.rfind('. ')
            last_newline = chunk.rfind('\n')
            break_at = max(last_period, last_newline)
            if break_at > chunk_size // 2:
                end = start + break_at + 1
                chunk = text[start:end]
        
        chunks.append(chunk)
        start = end - overlap
    
    return chunks


def workspace_search(
    query: str,
    path: str = ".",
    file_pattern: Optional[str] = None,
    content_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    max_results: int = 100,
    task_id: str = "default",
) -> str:
    """Workspace-wide search with multiple filters.
    
    Args:
        query: Search query (used for content if content_pattern not provided)
        path: Root path to search
        file_pattern: Glob pattern for files
        content_pattern: Regex pattern for content
        case_sensitive: Case sensitive search
        max_results: Maximum results
        task_id: Task identifier
        
    Returns:
        JSON string with search results
    """
    try:
        resolved = _resolve_path(path, task_id)
        if not resolved or not resolved.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        
        # Build ripgrep command for speed
        use_rg = _check_tool("rg")
        
        if use_rg:
            cmd = ["rg", "--json"]
            
            if not case_sensitive:
                cmd.append("-i")
            
            if file_pattern:
                cmd.extend(["-g", file_pattern])
            
            if content_pattern:
                cmd.append(content_pattern)
            else:
                cmd.append(query)
            
            cmd.extend(["--max-count", str(max_results)])
            
            # Add path
            cmd.append(str(resolved))
            
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            matches = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        data = json.loads(line)
                        if data.get("type") == "match":
                            match_data = data.get("data", {})
                            matches.append({
                                "file": match_data.get("path", {}).get("text", ""),
                                "line_number": match_data.get("line_number", 0),
                                "lines": match_data.get("lines", {}).get("text", ""),
                                "submatches": [
                                    {
                                        "start": m.get("start", 0),
                                        "end": m.get("end", 0),
                                        "match": m.get("match", {}).get("text", ""),
                                    }
                                    for m in match_data.get("submatches", [])
                                ],
                            })
                    except json.JSONDecodeError:
                        pass
            
            return json.dumps({"success": True, "matches": matches, "count": len(matches)})
        
        else:
            # Fallback to Python search
            matches = []
            flags = 0 if case_sensitive else re.IGNORECASE
            pattern = re.compile(content_pattern or query, flags)
            
            for file_path in resolved.rglob("*"):
                if file_path.is_file():
                    if file_pattern and not file_path.match(file_pattern):
                        continue
                    
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        for i, line in enumerate(content.splitlines(), 1):
                            if pattern.search(line):
                                matches.append({
                                    "file": str(file_path.relative_to(resolved)),
                                    "line_number": i,
                                    "line": line.strip(),
                                })
                                if len(matches) >= max_results:
                                    break
                    except Exception:
                        pass
                
                if len(matches) >= max_results:
                    break
            
            return json.dumps({"success": True, "matches": matches, "count": len(matches)})
        
    except Exception as e:
        logger.exception("Workspace search failed")
        return json.dumps({"error": str(e)})


def regex_search(
    pattern: str,
    path: str = ".",
    file_pattern: Optional[str] = None,
    case_sensitive: bool = False,
    max_results: int = 100,
    task_id: str = "default",
) -> str:
    """Regex search across files.
    
    Args:
        pattern: Regex pattern
        path: Root path
        file_pattern: File glob pattern
        case_sensitive: Case sensitive
        max_results: Max results
        task_id: Task identifier
        
    Returns:
        JSON string with matches
    """
    return workspace_search(
        query="",
        path=path,
        file_pattern=file_pattern,
        content_pattern=pattern,
        case_sensitive=case_sensitive,
        max_results=max_results,
        task_id=task_id,
    )


def dependency_search(
    dependency: str,
    path: str = ".",
    task_id: str = "default",
) -> str:
    """Search for dependency usage across project.
    
    Args:
        dependency: Dependency name to search for
        path: Root path
        task_id: Task identifier
        
    Returns:
        JSON string with usage locations
    """
    try:
        resolved = _resolve_path(path, task_id)
        if not resolved or not resolved.exists():
            return json.dumps({"error": f"Path not found: {path}"})
        
        results = []
        
        # Check package.json (Node.js)
        for pkg_json in resolved.rglob("package.json"):
            try:
                data = json.loads(pkg_json.read_text())
                deps = {**data.get("dependencies", {}), **data.get("devDependencies", {})}
                if dependency in deps:
                    results.append({
                        "file": str(pkg_json.relative_to(resolved)),
                        "type": "package.json",
                        "version": deps[dependency],
                    })
            except Exception:
                pass
        
        # Check requirements.txt / pyproject.toml (Python)
        for req_file in resolved.rglob("requirements*.txt"):
            try:
                content = req_file.read_text()
                if dependency.lower() in content.lower():
                    results.append({
                        "file": str(req_file.relative_to(resolved)),
                        "type": "requirements.txt",
                    })
            except Exception:
                pass
        
        for pyproject in resolved.rglob("pyproject.toml"):
            try:
                content = pyproject.read_text()
                if dependency in content:
                    results.append({
                        "file": str(pyproject.relative_to(resolved)),
                        "type": "pyproject.toml",
                    })
            except Exception:
                pass
        
        # Check Cargo.toml (Rust)
        for cargo in resolved.rglob("Cargo.toml"):
            try:
                content = cargo.read_text()
                if dependency in content:
                    results.append({
                        "file": str(cargo.relative_to(resolved)),
                        "type": "Cargo.toml",
                    })
            except Exception:
                pass
        
        # Check go.mod (Go)
        for gomod in resolved.rglob("go.mod"):
            try:
                content = gomod.read_text()
                if dependency in content:
                    results.append({
                        "file": str(gomod.relative_to(resolved)),
                        "type": "go.mod",
                    })
            except Exception:
                pass
        
        # Check pom.xml (Maven)
        for pom in resolved.rglob("pom.xml"):
            try:
                content = pom.read_text()
                if dependency in content:
                    results.append({
                        "file": str(pom.relative_to(resolved)),
                        "type": "pom.xml",
                    })
            except Exception:
                pass
        
        # Check build.gradle (Gradle)
        for gradle in resolved.rglob("build.gradle*"):
            try:
                content = gradle.read_text()
                if dependency in content:
                    results.append({
                        "file": str(gradle.relative_to(resolved)),
                        "type": "build.gradle",
                    })
            except Exception:
                pass
        
        return json.dumps({"success": True, "results": results})
        
    except Exception as e:
        logger.exception("Dependency search failed")
        return json.dumps({"error": str(e)})


def doc_search(
    query: str,
    path: str = ".",
    doc_types: Optional[List[str]] = None,
    max_results: int = 20,
    task_id: str = "default",
) -> str:
    """Search documentation files.
    
    Args:
        query: Search query
        path: Root path
        doc_types: Documentation types (markdown, rst, adoc, txt)
        max_results: Max results
        task_id: Task identifier
        
    Returns:
        JSON string with results
    """
    if doc_types is None:
        doc_types = ["markdown", "rst", "adoc", "txt"]
    
    extensions = []
    if "markdown" in doc_types:
        extensions.extend([".md", ".markdown", ".mdx"])
    if "rst" in doc_types:
        extensions.append(".rst")
    if "adoc" in doc_types:
        extensions.extend([".adoc", ".asciidoc"])
    if "txt" in doc_types:
        extensions.append(".txt")
    
    file_pattern = "*.{" + ",".join(ext[1:] for ext in extensions) + "}"
    
    return workspace_search(
        query=query,
        path=path,
        file_pattern=file_pattern,
        max_results=max_results,
        task_id=task_id,
    )


def code_search(
    query: str,
    path: str = ".",
    language: Optional[str] = None,
    max_results: int = 50,
    task_id: str = "default",
) -> str:
    """Search code with language-specific patterns.
    
    Args:
        query: Search query
        path: Root path
        language: Programming language
        max_results: Max results
        task_id: Task identifier
        
    Returns:
        JSON string with results
    """
    lang_extensions = {
        "python": [".py"],
        "javascript": [".js", ".jsx"],
        "typescript": [".ts", ".tsx"],
        "go": [".go"],
        "rust": [".rs"],
        "java": [".java"],
        "kotlin": [".kt", ".kts"],
        "swift": [".swift"],
        "cpp": [".cpp", ".cc", ".cxx", ".hpp", ".h"],
        "c": [".c", ".h"],
        "csharp": [".cs"],
        "php": [".php"],
        "ruby": [".rb"],
        "scala": [".scala"],
    }
    
    if language and language.lower() in lang_extensions:
        extensions = lang_extensions[language.lower()]
        file_pattern = "*.{" + ",".join(ext[1:] for ext in extensions) + "}"
    else:
        file_pattern = None
    
    return workspace_search(
        query=query,
        path=path,
        file_pattern=file_pattern,
        max_results=max_results,
        task_id=task_id,
    )


def _check_tool(name: str) -> bool:
    """Check if a command-line tool is available."""
    try:
        subprocess.run([name, "--version"], capture_output=True, check=False)
        return True
    except FileNotFoundError:
        return False


def _resolve_path(path: str, task_id: str) -> Optional[Path]:
    """Resolve path using Hermes path resolution."""
    try:
        return Path(_resolve_path_for_task(path, task_id)).resolve()
    except Exception:
        return None


def _register_search_tools():
    """Register all search tools."""
    tools = [
        ("semantic_search", semantic_search, "Semantic/vector search across workspace"),
        ("index_workspace", index_workspace, "Index workspace for semantic search"),
        ("workspace_search", workspace_search, "Workspace-wide search with filters"),
        ("regex_search", regex_search, "Regex search across files"),
        ("dependency_search", dependency_search, "Search for dependency usage"),
        ("doc_search", doc_search, "Search documentation files"),
        ("code_search", code_search, "Language-aware code search"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="search_enhanced",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_search_tools()