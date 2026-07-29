#!/usr/bin/env python3
"""
Documentation Generator Tools Module

Extends Hermes with automated documentation generation:
- README generation
- Architecture documentation
- API documentation
- Sequence diagrams (Mermaid)
- Class diagrams (Mermaid)
- Generic Mermaid diagrams
- Project summaries
- Dependency reports

All operations use the existing file operations, terminal tool, and LLM integration.
"""

import json
import logging
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

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


def _generate_with_llm(prompt: str, model: Optional[str] = None, max_tokens: int = 4000) -> str:
    """Generate content using LLM."""
    try:
        response = call_llm(
            prompt=prompt,
            model=model or os.getenv("AUXILIARY_DOC_MODEL"),
            max_tokens=max_tokens,
            temperature=0.3,
        )
        return response
    except Exception as e:
        logger.exception("LLM generation failed: %s", e)
        return f"# Generation Failed\n\nError: {e}"


def _analyze_project_structure(repo_path: Path) -> Dict[str, Any]:
    """Analyze project structure for documentation."""
    file_ops = _get_file_ops()
    
    structure = {
        "directories": [],
        "files": [],
        "languages": {},
        "key_files": [],
        "config_files": [],
        "docs": [],
        "tests": [],
    }
    
    # Common patterns
    ignore_dirs = {'.git', '__pycache__', 'node_modules', '.venv', 'venv', 'dist', 'build', 'target', '.next', '.cache'}
    ignore_files = {'.DS_Store', 'Thumbs.db'}
    
    for root, dirs, files in file_ops.walk(repo_path):
        root_path = Path(root)
        rel_root = root_path.relative_to(repo_path)
        
        # Filter ignored directories
        dirs[:] = [d for d in dirs if d not in ignore_dirs]
        
        if rel_root != Path('.'):
            structure["directories"].append(str(rel_root))
        
        for f in files:
            if f in ignore_files:
                continue
            file_path = root_path / f
            rel_file = file_path.relative_to(repo_path)
            structure["files"].append(str(rel_file))
            
            # Track languages by extension
            ext = file_path.suffix.lower()
            if ext:
                structure["languages"][ext] = structure["languages"].get(ext, 0) + 1
            
            # Identify key files
            if f.lower() in ['readme.md', 'readme.rst', 'readme.txt', 'license', 'license.md', 'license.txt',
                           'changelog.md', 'changelog.txt', 'contributing.md', 'code_of_conduct.md']:
                structure["key_files"].append(str(rel_file))
            
            # Config files
            if f in ['package.json', 'pyproject.toml', 'setup.py', 'requirements.txt', 'Cargo.toml',
                    'go.mod', 'pom.xml', 'build.gradle', 'Makefile', 'CMakeLists.txt',
                    'docker-compose.yml', 'Dockerfile', '.gitignore', '.env.example']:
                structure["config_files"].append(str(rel_file))
            
            # Documentation
            if ext in ['.md', '.rst', '.txt'] and 'doc' in str(rel_file).lower():
                structure["docs"].append(str(rel_file))
            
            # Tests
            if 'test' in f.lower() or 'spec' in f.lower():
                structure["tests"].append(str(rel_file))
    
    return structure


def generate_readme(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_badges: bool = True,
    include_toc: bool = True,
    include_install: bool = True,
    include_usage: bool = True,
    include_api: bool = False,
    include_contributing: bool = True,
    include_license: bool = True,
    style: str = "comprehensive",  # minimal, standard, comprehensive
    task_id: str = "default",
) -> str:
    """Generate a README file for the project."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        # Analyze project
        structure = _analyze_project_structure(resolved)
        
        # Detect project type
        project_type = "unknown"
        name = resolved.name
        description = ""
        
        if file_ops.exists(resolved / "package.json"):
            project_type = "node"
            try:
                pkg = json.loads(file_ops.read(resolved / "package.json"))
                name = pkg.get("name", name)
                description = pkg.get("description", "")
            except:
                pass
        elif file_ops.exists(resolved / "pyproject.toml") or file_ops.exists(resolved / "setup.py"):
            project_type = "python"
        elif file_ops.exists(resolved / "Cargo.toml"):
            project_type = "rust"
        elif file_ops.exists(resolved / "go.mod"):
            project_type = "go"
        elif file_ops.exists(resolved / "pom.xml"):
            project_type = "java"
        elif file_ops.exists(resolved / "composer.json"):
            project_type = "php"
        
        # Generate with LLM
        prompt = f"""Generate a {style} README.md for a {project_type} project.

Project Name: {name}
Description: {description or "No description available"}

Project Structure:
- Directories: {', '.join(structure['directories'][:20])}
- Key Files: {', '.join(structure['key_files'])}
- Config Files: {', '.join(structure['config_files'])}
- Languages: {', '.join(f'{k}: {v}' for k, v in sorted(structure['languages'].items(), key=lambda x: -x[1])[:10])}
- Documentation: {', '.join(structure['docs'][:10])}
- Tests: {', '.join(structure['tests'][:10])}

Include sections:
- Badges: {include_badges}
- Table of Contents: {include_toc}
- Installation: {include_install}
- Usage: {include_usage}
- API Reference: {include_api}
- Contributing: {include_contributing}
- License: {include_license}

Generate a well-formatted markdown README with appropriate sections for a {project_type} project.
Use proper markdown syntax, code blocks, and formatting.
"""
        
        readme_content = _generate_with_llm(prompt)
        
        # Determine output path
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / "README.md"
        
        # Write file
        file_ops.write(out_path, readme_content)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "project_type": project_type,
            "style": style,
        })
    
    except Exception as e:
        logger.exception("generate_readme error: %s", e)
        return json.dumps({"error": f"README generation failed: {e}"})


def generate_architecture_docs(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_overview: bool = True,
    include_components: bool = True,
    include_data_flow: bool = True,
    include_deployment: bool = True,
    include_mermaid: bool = True,
    task_id: str = "default",
) -> str:
    """Generate architecture documentation."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        structure = _analyze_project_structure(resolved)
        
        prompt = f"""Generate architecture documentation (ARCHITECTURE.md) for this project.

Project Structure:
- Directories: {', '.join(structure['directories'][:30])}
- Languages: {', '.join(f'{k}: {v}' for k, v in sorted(structure['languages'].items(), key=lambda x: -x[1])[:15])}
- Config Files: {', '.join(structure['config_files'])}

Include sections:
- Overview: {include_overview}
- Components: {include_components}
- Data Flow: {include_data_flow}
- Deployment: {include_deployment}
- Mermaid Diagrams: {include_mermaid}

Generate comprehensive architecture documentation in markdown format.
If Mermaid is enabled, include component diagrams, sequence diagrams, and deployment diagrams.
Focus on the actual project structure and technologies detected.
"""
        
        arch_content = _generate_with_llm(prompt, max_tokens=6000)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / "ARCHITECTURE.md"
        
        file_ops.write(out_path, arch_content)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
        })
    
    except Exception as e:
        logger.exception("generate_architecture_docs error: %s", e)
        return json.dumps({"error": f"Architecture docs generation failed: {e}"})


def generate_api_docs(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_endpoints: bool = True,
    include_models: bool = True,
    include_auth: bool = True,
    include_examples: bool = True,
    format: str = "markdown",  # markdown, openapi
    task_id: str = "default",
) -> str:
    """Generate API documentation from code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        # Find API-related files
        api_files = []
        for root, dirs, files in file_ops.walk(resolved):
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.go', '.java', '.rb', '.php')):
                    full = Path(root) / f
                    try:
                        content = file_ops.read(full)
                        if any(kw in content.lower() for kw in ['@app.route', '@router.', 'fastapi', 'flask', 'express', 'gin', 'spring', 'controller']):
                            api_files.append(str(full.relative_to(resolved)))
                    except:
                        pass
        
        prompt = f"""Generate API documentation for this project.

API Files Found: {', '.join(api_files[:20])}

Include sections:
- Endpoints: {include_endpoints}
- Data Models: {include_models}
- Authentication: {include_auth}
- Examples: {include_examples}
- Format: {format}

Generate comprehensive API documentation in {format} format.
If OpenAPI format requested, generate valid OpenAPI 3.0 specification.
Otherwise, generate markdown with endpoint tables, request/response examples, and authentication details.
"""
        
        api_content = _generate_with_llm(prompt, max_tokens=8000)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            ext = ".yaml" if format == "openapi" else ".md"
            out_path = resolved / f"API_DOCS{ext}"
        
        file_ops.write(out_path, api_content)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "format": format,
        })
    
    except Exception as e:
        logger.exception("generate_api_docs error: %s", e)
        return json.dumps({"error": f"API docs generation failed: {e}"})


def generate_sequence_diagram(
    repo_path: str = ".",
    scenario: str = "",
    output_path: Optional[str] = None,
    actors: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Generate a Mermaid sequence diagram."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        structure = _analyze_project_structure(resolved)
        
        prompt = f"""Generate a Mermaid sequence diagram for this scenario.

Scenario: {scenario or "Typical request flow through the application"}

Project Context:
- Languages: {', '.join(f'{k}: {v}' for k, v in sorted(structure['languages'].items(), key=lambda x: -x[1])[:10])}
- Key Components: {', '.join(structure['directories'][:15])}
- Actors: {', '.join(actors) if actors else 'User, Frontend, API, Database, External Services'}

Generate a Mermaid sequence diagram showing the flow.
Use proper Mermaid syntax with participants, messages, activations, and notes.
Return only the Mermaid code block.
"""
        
        diagram = _generate_with_llm(prompt, max_tokens=3000)
        
        # Extract Mermaid code if wrapped
        mermaid_match = re.search(r'```mermaid\n(.*?)\n```', diagram, re.DOTALL)
        if mermaid_match:
            diagram = mermaid_match.group(1)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / "sequence_diagram.mmd"
        
        file_ops.write(out_path, diagram)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "diagram": diagram,
        })
    
    except Exception as e:
        logger.exception("generate_sequence_diagram error: %s", e)
        return json.dumps({"error": f"Sequence diagram generation failed: {e}"})


def generate_class_diagram(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_methods: bool = True,
    include_attributes: bool = True,
    include_relationships: bool = True,
    max_classes: int = 50,
    task_id: str = "default",
) -> str:
    """Generate a Mermaid class diagram from code."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        # Extract class definitions
        classes = []
        for root, dirs, files in file_ops.walk(resolved):
            for f in files:
                if f.endswith(('.py', '.js', '.ts', '.java', '.cs', '.php', '.rb')):
                    full = Path(root) / f
                    try:
                        content = file_ops.read(full)
                        # Simple class extraction
                        for line in content.split('\n'):
                            line = line.strip()
                            if re.match(r'^(class|interface|struct|type)\s+\w+', line):
                                classes.append({
                                    "file": str(full.relative_to(resolved)),
                                    "definition": line,
                                })
                                if len(classes) >= max_classes:
                                    break
                    except:
                        pass
        
        prompt = f"""Generate a Mermaid class diagram from these class definitions.

Classes Found ({len(classes)}):
{chr(10).join(f"- {c['file']}: {c['definition']}" for c in classes[:30])}

Include:
- Methods: {include_methods}
- Attributes: {include_attributes}
- Relationships: {include_relationships}

Generate a Mermaid class diagram showing classes, their attributes, methods, and relationships (inheritance, composition, association).
Return only the Mermaid code block.
"""
        
        diagram = _generate_with_llm(prompt, max_tokens=5000)
        
        mermaid_match = re.search(r'```mermaid\n(.*?)\n```', diagram, re.DOTALL)
        if mermaid_match:
            diagram = mermaid_match.group(1)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / "class_diagram.mmd"
        
        file_ops.write(out_path, diagram)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "diagram": diagram,
        })
    
    except Exception as e:
        logger.exception("generate_class_diagram error: %s", e)
        return json.dumps({"error": f"Class diagram generation failed: {e}"})


def generate_mermaid_diagram(
    diagram_type: str,  # flowchart, sequence, class, state, er, journey, gantt, pie, gitgraph, mindmap
    description: str,
    output_path: Optional[str] = None,
    repo_path: str = ".",
    task_id: str = "default",
) -> str:
    """Generate a generic Mermaid diagram."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        prompt = f"""Generate a Mermaid {diagram_type} diagram.

Description: {description}

Generate valid Mermaid {diagram_type} syntax.
Return only the Mermaid code block.
"""
        
        diagram = _generate_with_llm(prompt, max_tokens=3000)
        
        mermaid_match = re.search(r'```mermaid\n(.*?)\n```', diagram, re.DOTALL)
        if mermaid_match:
            diagram = mermaid_match.group(1)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / f"{diagram_type}_diagram.mmd"
        
        file_ops.write(out_path, diagram)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "diagram": diagram,
            "type": diagram_type,
        })
    
    except Exception as e:
        logger.exception("generate_mermaid_diagram error: %s", e)
        return json.dumps({"error": f"Mermaid diagram generation failed: {e}"})


def generate_project_summary(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_stats: bool = True,
    include_structure: bool = True,
    include_dependencies: bool = True,
    include_recent_changes: bool = True,
    task_id: str = "default",
) -> str:
    """Generate a project summary document."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        structure = _analyze_project_structure(resolved)
        
        # Get git stats
        git_stats = {}
        if file_ops.exists(resolved / ".git"):
            try:
                result = _run_command(f"cd {resolved} && git log --oneline -20", task_id)
                if result.get("success"):
                    git_stats["recent_commits"] = result.get("stdout", "")
                
                result = _run_command(f"cd {resolved} && git log --since='30 days ago' --pretty=format:'%an' | sort | uniq -c | sort -rn", task_id)
                if result.get("success"):
                    git_stats["contributors_30d"] = result.get("stdout", "")
            except:
                pass
        
        prompt = f"""Generate a project summary document (SUMMARY.md).

Project: {resolved.name}
Structure:
- Directories: {len(structure['directories'])}
- Files: {len(structure['files'])}
- Languages: {', '.join(f'{k}: {v}' for k, v in sorted(structure['languages'].items(), key=lambda x: -x[1])[:15])}
- Config Files: {', '.join(structure['config_files'][:10])}

Git Stats:
{json.dumps(git_stats, indent=2)}

Include sections:
- Statistics: {include_stats}
- Structure: {include_structure}
- Dependencies: {include_dependencies}
- Recent Changes: {include_recent_changes}

Generate a comprehensive project summary in markdown format.
"""
        
        summary = _generate_with_llm(prompt, max_tokens=5000)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            out_path = resolved / "SUMMARY.md"
        
        file_ops.write(out_path, summary)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
        })
    
    except Exception as e:
        logger.exception("generate_project_summary error: %s", e)
        return json.dumps({"error": f"Project summary generation failed: {e}"})


def generate_dependency_report(
    repo_path: str = ".",
    output_path: Optional[str] = None,
    include_versions: bool = True,
    include_vulnerabilities: bool = False,
    include_licenses: bool = True,
    include_outdated: bool = True,
    format: str = "markdown",  # markdown, json, csv
    task_id: str = "default",
) -> str:
    """Generate a dependency report."""
    try:
        resolved = _resolve_path(repo_path, task_id)
        file_ops = _get_file_ops(task_id)
        
        if not file_ops.exists(resolved):
            return json.dumps({"error": f"Path not found: {repo_path}"})
        
        # Find dependency files
        dep_files = []
        for f in ['package.json', 'package-lock.json', 'yarn.lock', 'pnpm-lock.yaml',
                  'requirements.txt', 'pyproject.toml', 'poetry.lock', 'Pipfile.lock',
                  'Cargo.toml', 'Cargo.lock', 'go.mod', 'go.sum',
                  'pom.xml', 'build.gradle', 'build.gradle.kts',
                  'composer.json', 'composer.lock']:
            if file_ops.exists(resolved / f):
                dep_files.append(f)
        
        # Read dependency files
        deps_content = {}
        for f in dep_files:
            try:
                deps_content[f] = file_ops.read(resolved / f)
            except:
                pass
        
        prompt = f"""Generate a dependency report for this project.

Dependency Files: {', '.join(dep_files)}

Dependencies:
{json.dumps(deps_content, indent=2)[:5000]}

Include:
- Versions: {include_versions}
- Vulnerabilities: {include_vulnerabilities}
- Licenses: {include_licenses}
- Outdated: {include_outdated}
- Format: {format}

Generate a comprehensive dependency report in {format} format.
Include tables with dependency name, version, license, and status.
"""
        
        report = _generate_with_llm(prompt, max_tokens=6000)
        
        if output_path:
            out_path = _resolve_path(output_path, task_id)
        else:
            ext = ".json" if format == "json" else ".csv" if format == "csv" else ".md"
            out_path = resolved / f"DEPENDENCY_REPORT{ext}"
        
        file_ops.write(out_path, report)
        
        return json.dumps({
            "success": True,
            "path": str(out_path),
            "format": format,
        })
    
    except Exception as e:
        logger.exception("generate_dependency_report error: %s", e)
        return json.dumps({"error": f"Dependency report generation failed: {e}"})


# Register all tools
def _register_doc_tools():
    """Register all documentation tools with the registry."""

    tools = [
        ("generate_readme", "documentation", {
            "name": "generate_readme",
            "description": "Generate a README.md file for the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_badges": {"type": "boolean", "description": "Include badges", "default": True},
                    "include_toc": {"type": "boolean", "description": "Include table of contents", "default": True},
                    "include_install": {"type": "boolean", "description": "Include installation section", "default": True},
                    "include_usage": {"type": "boolean", "description": "Include usage section", "default": True},
                    "include_api": {"type": "boolean", "description": "Include API section", "default": False},
                    "include_contributing": {"type": "boolean", "description": "Include contributing section", "default": True},
                    "include_license": {"type": "boolean", "description": "Include license section", "default": True},
                    "style": {"type": "string", "enum": ["minimal", "standard", "comprehensive"], "default": "comprehensive"},
                },
                "required": [],
            },
        }, generate_readme, None, [], False, "📄", None),

        ("generate_architecture_docs", "documentation", {
            "name": "generate_architecture_docs",
            "description": "Generate architecture documentation (ARCHITECTURE.md)",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_overview": {"type": "boolean", "description": "Include overview", "default": True},
                    "include_components": {"type": "boolean", "description": "Include components", "default": True},
                    "include_data_flow": {"type": "boolean", "description": "Include data flow", "default": True},
                    "include_deployment": {"type": "boolean", "description": "Include deployment", "default": True},
                    "include_mermaid": {"type": "boolean", "description": "Include Mermaid diagrams", "default": True},
                },
                "required": [],
            },
        }, generate_architecture_docs, None, [], False, "🏗️", None),

        ("generate_api_docs", "documentation", {
            "name": "generate_api_docs",
            "description": "Generate API documentation from code",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_endpoints": {"type": "boolean", "description": "Include endpoints", "default": True},
                    "include_models": {"type": "boolean", "description": "Include data models", "default": True},
                    "include_auth": {"type": "boolean", "description": "Include authentication", "default": True},
                    "include_examples": {"type": "boolean", "description": "Include examples", "default": True},
                    "format": {"type": "string", "enum": ["markdown", "openapi"], "default": "markdown"},
                },
                "required": [],
            },
        }, generate_api_docs, None, [], False, "📚", None),

        ("generate_sequence_diagram", "documentation", {
            "name": "generate_sequence_diagram",
            "description": "Generate a Mermaid sequence diagram",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "scenario": {"type": "string", "description": "Scenario description", "default": ""},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "actors": {"type": "array", "items": {"type": "string"}, "description": "Actors in diagram", "default": None},
                },
                "required": [],
            },
        }, generate_sequence_diagram, None, [], False, "📊", None),

        ("generate_class_diagram", "documentation", {
            "name": "generate_class_diagram",
            "description": "Generate a Mermaid class diagram from code",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_methods": {"type": "boolean", "description": "Include methods", "default": True},
                    "include_attributes": {"type": "boolean", "description": "Include attributes", "default": True},
                    "include_relationships": {"type": "boolean", "description": "Include relationships", "default": True},
                    "max_classes": {"type": "integer", "description": "Max classes to include", "default": 50},
                },
                "required": [],
            },
        }, generate_class_diagram, None, [], False, "📐", None),

        ("generate_mermaid_diagram", "documentation", {
            "name": "generate_mermaid_diagram",
            "description": "Generate a generic Mermaid diagram",
            "parameters": {
                "type": "object",
                "properties": {
                    "diagram_type": {"type": "string", "enum": ["flowchart", "sequence", "class", "state", "er", "journey", "gantt", "pie", "gitgraph", "mindmap"]},
                    "description": {"type": "string", "description": "Diagram description"},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                },
                "required": ["diagram_type", "description"],
            },
        }, generate_mermaid_diagram, None, [], False, "🎨", None),

        ("generate_project_summary", "documentation", {
            "name": "generate_project_summary",
            "description": "Generate a project summary document",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_stats": {"type": "boolean", "description": "Include statistics", "default": True},
                    "include_structure": {"type": "boolean", "description": "Include structure", "default": True},
                    "include_dependencies": {"type": "boolean", "description": "Include dependencies", "default": True},
                    "include_recent_changes": {"type": "boolean", "description": "Include recent changes", "default": True},
                },
                "required": [],
            },
        }, generate_project_summary, None, [], False, "📋", None),

        ("generate_dependency_report", "documentation", {
            "name": "generate_dependency_report",
            "description": "Generate a dependency report",
            "parameters": {
                "type": "object",
                "properties": {
                    "repo_path": {"type": "string", "description": "Repository path", "default": "."},
                    "output_path": {"type": "string", "description": "Output file path", "default": None},
                    "include_versions": {"type": "boolean", "description": "Include versions", "default": True},
                    "include_vulnerabilities": {"type": "boolean", "description": "Include vulnerabilities", "default": False},
                    "include_licenses": {"type": "boolean", "description": "Include licenses", "default": True},
                    "include_outdated": {"type": "boolean", "description": "Include outdated", "default": True},
                    "format": {"type": "string", "enum": ["markdown", "json", "csv"], "default": "markdown"},
                },
                "required": [],
            },
        }, generate_dependency_report, None, [], False, "📦", None),
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
_register_doc_tools()

__all__ = [
    "generate_readme",
    "generate_architecture_docs",
    "generate_api_docs",
    "generate_sequence_diagram",
    "generate_class_diagram",
    "generate_mermaid_diagram",
    "generate_project_summary",
    "generate_dependency_report",
]

if __name__ == "__main__":
    print("Documentation tools loaded successfully")