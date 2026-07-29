#!/usr/bin/env python3
"""
MCP (Model Context Protocol) Integration Tools

Provides tools for connecting to and using MCP servers:
- Connect to MCP servers
- List available MCP tools
- Call MCP tools
- Pre-configured connections for popular services
"""

import json
import logging
import os
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Global MCP connections
_mcp_connections: Dict[str, Dict] = {}
_mcp_lock = threading.Lock()

# Pre-configured MCP servers
PRECONFIGURED_SERVERS = {
    "github": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-github"],
        "env": {"GITHUB_PERSONAL_ACCESS_TOKEN": "${GITHUB_TOKEN}"},
        "description": "GitHub API access (repos, issues, PRs, etc.)",
    },
    "gitlab": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gitlab"],
        "env": {"GITLAB_PERSONAL_ACCESS_TOKEN": "${GITLAB_TOKEN}"},
        "description": "GitLab API access",
    },
    "slack": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-slack"],
        "env": {"SLACK_BOT_TOKEN": "${SLACK_BOT_TOKEN}", "SLACK_TEAM_ID": "${SLACK_TEAM_ID}"},
        "description": "Slack workspace access",
    },
    "discord": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-discord"],
        "env": {"DISCORD_BOT_TOKEN": "${DISCORD_BOT_TOKEN}"},
        "description": "Discord bot access",
    },
    "notion": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-notion"],
        "env": {"NOTION_API_KEY": "${NOTION_API_KEY}"},
        "description": "Notion workspace access",
    },
    "jira": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-jira"],
        "env": {
            "JIRA_URL": "${JIRA_URL}",
            "JIRA_USERNAME": "${JIRA_USERNAME}",
            "JIRA_API_TOKEN": "${JIRA_API_TOKEN}",
        },
        "description": "Jira issue tracking",
    },
    "linear": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-linear"],
        "env": {"LINEAR_API_KEY": "${LINEAR_API_KEY}"},
        "description": "Linear issue tracking",
    },
    "figma": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-figma"],
        "env": {"FIGMA_API_TOKEN": "${FIGMA_API_TOKEN}"},
        "description": "Figma design files",
    },
    "google-drive": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gdrive"],
        "env": {"GDRIVE_CREDENTIALS": "${GDRIVE_CREDENTIALS}"},
        "description": "Google Drive access",
    },
    "gmail": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gmail"],
        "env": {
            "GMAIL_CLIENT_ID": "${GMAIL_CLIENT_ID}",
            "GMAIL_CLIENT_SECRET": "${GMAIL_CLIENT_SECRET}",
            "GMAIL_REFRESH_TOKEN": "${GMAIL_REFRESH_TOKEN}",
        },
        "description": "Gmail access",
    },
    "databricks": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-databricks"],
        "env": {"DATABRICKS_HOST": "${DATABRICKS_HOST}", "DATABRICKS_TOKEN": "${DATABRICKS_TOKEN}"},
        "description": "Databricks workspace",
    },
    "snowflake": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-snowflake"],
        "env": {
            "SNOWFLAKE_ACCOUNT": "${SNOWFLAKE_ACCOUNT}",
            "SNOWFLAKE_USER": "${SNOWFLAKE_USER}",
            "SNOWFLAKE_PASSWORD": "${SNOWFLAKE_PASSWORD}",
            "SNOWFLAKE_WAREHOUSE": "${SNOWFLAKE_WAREHOUSE}",
        },
        "description": "Snowflake data warehouse",
    },
    "salesforce": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-salesforce"],
        "env": {
            "SALESFORCE_CLIENT_ID": "${SALESFORCE_CLIENT_ID}",
            "SALESFORCE_CLIENT_SECRET": "${SALESFORCE_CLIENT_SECRET}",
            "SALESFORCE_REFRESH_TOKEN": "${SALESFORCE_REFRESH_TOKEN}",
        },
        "description": "Salesforce CRM",
    },
    "servicenow": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-servicenow"],
        "env": {
            "SERVICENOW_INSTANCE": "${SERVICENOW_INSTANCE}",
            "SERVICENOW_USERNAME": "${SERVICENOW_USERNAME}",
            "SERVICENOW_PASSWORD": "${SERVICENOW_PASSWORD}",
        },
        "description": "ServiceNow ITSM",
    },
    "aws": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-aws"],
        "env": {
            "AWS_ACCESS_KEY_ID": "${AWS_ACCESS_KEY_ID}",
            "AWS_SECRET_ACCESS_KEY": "${AWS_SECRET_ACCESS_KEY}",
            "AWS_REGION": "${AWS_REGION}",
        },
        "description": "AWS cloud services",
    },
    "gcp": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-gcp"],
        "env": {"GCP_PROJECT_ID": "${GCP_PROJECT_ID}", "GCP_CREDENTIALS": "${GCP_CREDENTIALS}"},
        "description": "Google Cloud Platform",
    },
    "azure": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-azure"],
        "env": {
            "AZURE_TENANT_ID": "${AZURE_TENANT_ID}",
            "AZURE_CLIENT_ID": "${AZURE_CLIENT_ID}",
            "AZURE_CLIENT_SECRET": "${AZURE_CLIENT_SECRET}",
            "AZURE_SUBSCRIPTION_ID": "${AZURE_SUBSCRIPTION_ID}",
        },
        "description": "Microsoft Azure",
    },
    "postgres": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-postgres"],
        "env": {"POSTGRES_CONNECTION_STRING": "${POSTGRES_CONNECTION_STRING}"},
        "description": "PostgreSQL database",
    },
    "sqlite": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-sqlite"],
        "env": {"SQLITE_DB_PATH": "${SQLITE_DB_PATH}"},
        "description": "SQLite database",
    },
    "redis": {
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-redis"],
        "env": {"REDIS_URL": "${REDIS_URL}"},
        "description": "Redis cache",
    },
}


def _resolve_env_vars(config: Dict) -> Dict:
    """Resolve environment variable references in config."""
    import re
    
    def resolve_value(val):
        if isinstance(val, str):
            # Replace ${VAR} with environment variable
            def replacer(match):
                var_name = match.group(1)
                return os.environ.get(var_name, match.group(0))
            return re.sub(r'\$\{([^}]+)\}', replacer, val)
        elif isinstance(val, dict):
            return {k: resolve_value(v) for k, v in val.items()}
        elif isinstance(val, list):
            return [resolve_value(v) for v in val]
        return val
    
    return resolve_value(config)


def mcp_connect(
    name: str,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    env: Optional[Dict[str, str]] = None,
    cwd: Optional[str] = None,
    use_preset: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Connect to an MCP server.
    
    Args:
        name: Connection name
        command: Command to start server
        args: Command arguments
        env: Environment variables
        cwd: Working directory
        use_preset: Use pre-configured server (github, gitlab, slack, etc.)
        task_id: Task identifier
        
    Returns:
        JSON string with connection result
    """
    with _mcp_lock:
        if name in _mcp_connections:
            return json.dumps({"error": f"Connection {name} already exists"})
    
    # Use preset if specified
    if use_preset:
        if use_preset not in PRECONFIGURED_SERVERS:
            return json.dumps({"error": f"Unknown preset: {use_preset}"})
        
        preset = PRECONFIGURED_SERVERS[use_preset]
        command = command or preset["command"]
        args = args or preset["args"]
        env = env or preset["env"]
    
    if not command:
        return json.dumps({"error": "command required"})
    
    # Resolve environment variables
    resolved_env = _resolve_env_vars(env or {})
    merged_env = {**os.environ, **resolved_env}
    
    try:
        # Start MCP server process
        process = subprocess.Popen(
            [command] + (args or []),
            env=merged_env,
            cwd=cwd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
        )
        
        # Wait a bit for server to start
        time.sleep(1)
        
        # Check if process is still alive
        if process.poll() is not None:
            stderr = process.stderr.read() if process.stderr else ""
            return json.dumps({
                "error": f"MCP server failed to start: {stderr}",
                "returncode": process.returncode,
            })
        
        # Initialize connection
        init_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "hermes-agent", "version": "1.0"},
            },
        }
        
        process.stdin.write(json.dumps(init_request) + "\n")
        process.stdin.flush()
        
        # Read response
        response_line = process.stdout.readline()
        if not response_line:
            process.terminate()
            return json.dumps({"error": "No response from MCP server"})
        
        try:
            response = json.loads(response_line)
            if "error" in response:
                process.terminate()
                return json.dumps({"error": f"MCP init failed: {response['error']}"})
        except json.JSONDecodeError:
            process.terminate()
            return json.dumps({"error": "Invalid MCP response"})
        
        # Store connection
        connection = {
            "name": name,
            "process": process,
            "command": command,
            "args": args,
            "env": resolved_env,
            "cwd": cwd,
            "preset": use_preset,
            "created": time.time(),
            "tools": [],
        }
        
        with _mcp_lock:
            _mcp_connections[name] = connection
        
        # List tools
        tools_result = mcp_list_tools(name, task_id)
        
        return json.dumps({
            "success": True,
            "connection": name,
            "preset": use_preset,
            "tools": json.loads(tools_result).get("tools", []),
        })
        
    except Exception as e:
        logger.exception(f"Failed to connect to MCP server {name}")
        return json.dumps({"error": str(e)})


def mcp_list_tools(
    name: str,
    task_id: str = "default",
) -> str:
    """List available tools from an MCP server.
    
    Args:
        name: Connection name
        task_id: Task identifier
        
    Returns:
        JSON string with tools list
    """
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/list",
            "params": {},
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response from MCP server"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": f"MCP error: {response['error']}"})
        
        tools = response.get("result", {}).get("tools", [])
        
        # Update connection cache
        conn["tools"] = tools
        
        return json.dumps({
            "success": True,
            "connection": name,
            "tools": tools,
        })
        
    except Exception as e:
        logger.exception(f"Failed to list MCP tools for {name}")
        return json.dumps({"error": str(e)})


def mcp_call_tool(
    name: str,
    tool: str,
    arguments: Dict,
    task_id: str = "default",
) -> str:
    """Call a tool on an MCP server.
    
    Args:
        name: Connection name
        tool: Tool name
        arguments: Tool arguments
        task_id: Task identifier
        
    Returns:
        JSON string with tool result
    """
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": int(time.time() * 1000),
            "method": "tools/call",
            "params": {
                "name": tool,
                "arguments": arguments,
            },
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        # Read response (may be multiple lines for streaming)
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response from MCP server"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": f"MCP tool error: {response['error']}"})
        
        result = response.get("result", {})
        
        return json.dumps({
            "success": True,
            "connection": name,
            "tool": tool,
            "result": result,
        })
        
    except Exception as e:
        logger.exception(f"Failed to call MCP tool {tool} on {name}")
        return json.dumps({"error": str(e)})


def mcp_disconnect(
    name: str,
    task_id: str = "default",
) -> str:
    """Disconnect from an MCP server.
    
    Args:
        name: Connection name
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    with _mcp_lock:
        conn = _mcp_connections.pop(name, None)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        process.terminate()
        process.wait(timeout=5)
        return json.dumps({"success": True, "disconnected": name})
    except Exception as e:
        logger.exception(f"Error disconnecting {name}")
        return json.dumps({"error": str(e)})


def mcp_list_connections(task_id: str = "default") -> str:
    """List all active MCP connections."""
    with _mcp_lock:
        connections = {
            name: {
                "name": conn["name"],
                "preset": conn.get("preset"),
                "command": conn["command"],
                "args": conn["args"],
                "tools_count": len(conn.get("tools", [])),
                "created": conn["created"],
                "alive": conn["process"].poll() is None,
            }
            for name, conn in _mcp_connections.items()
        }
    
    return json.dumps({"success": True, "connections": connections})


def mcp_presets(task_id: str = "default") -> str:
    """List available pre-configured MCP servers."""
    presets = {
        name: {
            "name": name,
            "description": config["description"],
            "command": config["command"],
            "args": config["args"],
            "env_vars": list(config["env"].keys()),
        }
        for name, config in PRECONFIGURED_SERVERS.items()
    }
    
    return json.dumps({"success": True, "presets": presets})


def mcp_install_preset(
    preset: str,
    name: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Install a pre-configured MCP server."""
    return mcp_connect(name or preset, use_preset=preset, task_id=task_id)


def mcp_resources_list(
    name: str,
    task_id: str = "default",
) -> str:
    """List available resources from MCP server."""
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "resources/list",
            "params": {},
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": response["error"]})
        
        return json.dumps({
            "success": True,
            "resources": response.get("result", {}).get("resources", []),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def mcp_resource_read(
    name: str,
    uri: str,
    task_id: str = "default",
) -> str:
    """Read a resource from MCP server."""
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "resources/read",
            "params": {"uri": uri},
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": response["error"]})
        
        return json.dumps({
            "success": True,
            "resource": response.get("result", {}),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def mcp_prompts_list(
    name: str,
    task_id: str = "default",
) -> str:
    """List available prompts from MCP server."""
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": 5,
            "method": "prompts/list",
            "params": {},
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": response["error"]})
        
        return json.dumps({
            "success": True,
            "prompts": response.get("result", {}).get("prompts", []),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def mcp_prompt_get(
    name: str,
    prompt: str,
    arguments: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Get a prompt from MCP server."""
    with _mcp_lock:
        conn = _mcp_connections.get(name)
    
    if not conn:
        return json.dumps({"error": f"Connection {name} not found"})
    
    try:
        process = conn["process"]
        
        request = {
            "jsonrpc": "2.0",
            "id": 6,
            "method": "prompts/get",
            "params": {
                "name": prompt,
                "arguments": arguments or {},
            },
        }
        
        process.stdin.write(json.dumps(request) + "\n")
        process.stdin.flush()
        
        response_line = process.stdout.readline()
        if not response_line:
            return json.dumps({"error": "No response"})
        
        response = json.loads(response_line)
        
        if "error" in response:
            return json.dumps({"error": response["error"]})
        
        return json.dumps({
            "success": True,
            "prompt": response.get("result", {}),
        })
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def _register_mcp_tools():
    """Register MCP integration tools."""
    tools = [
        ("mcp_connect", mcp_connect, "Connect to an MCP server"),
        ("mcp_list_tools", mcp_list_tools, "List tools from MCP server"),
        ("mcp_call_tool", mcp_call_tool, "Call a tool on MCP server"),
        ("mcp_disconnect", mcp_disconnect, "Disconnect from MCP server"),
        ("mcp_list_connections", mcp_list_connections, "List active MCP connections"),
        ("mcp_presets", mcp_presets, "List pre-configured MCP servers"),
        ("mcp_install_preset", mcp_install_preset, "Install a pre-configured MCP server"),
        ("mcp_resources_list", mcp_resources_list, "List resources from MCP server"),
        ("mcp_resource_read", mcp_resource_read, "Read a resource from MCP server"),
        ("mcp_prompts_list", mcp_prompts_list, "List prompts from MCP server"),
        ("mcp_prompt_get", mcp_prompt_get, "Get a prompt from MCP server"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="mcp",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_mcp_tools()