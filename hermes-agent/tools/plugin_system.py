#!/usr/bin/env python3
"""
Plugin System Module

Provides dynamic plugin loading and management:
- Plugin discovery and loading
- Tool registration from plugins
- Plugin lifecycle management
- Plugin configuration
"""

import importlib
import importlib.util
import json
import logging
import os
import sys
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set

from tools.registry import registry, ToolEntry

logger = logging.getLogger(__name__)

# Plugin directories (searched in order)
PLUGIN_DIRS = [
    Path.home() / ".hermes" / "plugins",
    Path(__file__).parent.parent / "plugins",
    Path.cwd() / "plugins",
]

# Additional dirs from environment
if "HERMES_PLUGIN_DIRS" in os.environ:
    for d in os.environ["HERMES_PLUGIN_DIRS"].split(":"):
        PLUGIN_DIRS.insert(0, Path(d).expanduser())

_loaded_plugins: Dict[str, Any] = {}
_plugin_lock = threading.Lock()
_plugin_tools: Dict[str, List[str]] = {}  # plugin_name -> tool_names
_plugin_config: Dict[str, Dict] = {}  # plugin_name -> config


class PluginContext:
    """Context provided to plugins during registration."""
    
    def __init__(self, plugin_name: str):
        self.plugin_name = plugin_name
        self.registered_tools: List[str] = []
        self.registered_commands: List[str] = []
        self.config = _plugin_config.get(plugin_name, {})
    
    def register_tool(self, name: str, func: Callable, schema: Dict, 
                      description: str = "", toolset: str = None,
                      check_fn: Callable = None, requires_env: List[str] = None,
                      is_async: bool = False, emoji: str = None,
                      max_result_size_chars: int = None) -> None:
        """Register a tool from the plugin."""
        full_name = f"{self.plugin_name}.{name}" if not name.startswith(self.plugin_name) else name
        
        # Create handler wrapper
        def handler(args: Dict, **kwargs) -> str:
            try:
                return func(args, **kwargs)
            except Exception as e:
                logger.exception(f"Plugin tool {full_name} failed")
                return json.dumps({"error": str(e)})
        
        registry.register(
            name=full_name,
            toolset=toolset or self.plugin_name,
            schema={"name": full_name, "description": description or name, "parameters": schema},
            handler=handler,
            check_fn=check_fn,
            requires_env=requires_env or [],
            is_async=is_async,
            description=description or name,
            emoji=emoji,
            max_result_size_chars=max_result_size_chars,
        )
        
        self.registered_tools.append(full_name)
        _plugin_tools.setdefault(self.plugin_name, []).append(full_name)
    
    def register_cli_command(self, name: str, func: Callable, 
                             help_text: str = "", args: List[Dict] = None) -> None:
        """Register a CLI command (for CLI plugin integration)."""
        # This would integrate with the CLI command system
        # For now, just track it
        self.registered_commands.append(name)
        logger.info(f"Plugin {self.plugin_name} registered CLI command: {name}")
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """Get plugin configuration value."""
        return self.config.get(key, default)
    
    def set_config(self, key: str, value: Any) -> None:
        """Set plugin configuration value."""
        self.config[key] = value
        _plugin_config[self.plugin_name] = self.config


def discover_plugins(plugin_dirs: Optional[List[Path]] = None) -> List[str]:
    """Discover available plugins in plugin directories.
    
    Args:
        plugin_dirs: Directories to search (uses defaults if None)
        
    Returns:
        List of discovered plugin names
    """
    dirs = plugin_dirs or PLUGIN_DIRS
    plugins = []
    
    for plugin_dir in dirs:
        if not plugin_dir.exists() or not plugin_dir.is_dir():
            continue
        
        for item in plugin_dir.iterdir():
            if item.is_dir() and not item.name.startswith("."):
                # Check for plugin.yaml or __init__.py
                if (item / "plugin.yaml").exists() or (item / "__init__.py").exists():
                    plugins.append(item.name)
            elif item.suffix == ".py" and not item.name.startswith("_"):
                # Single-file plugin
                plugins.append(item.stem)
    
    return sorted(set(plugins))


def load_plugin(plugin_name: str, plugin_dirs: Optional[List[Path]] = None) -> bool:
    """Load a plugin by name.
    
    Args:
        plugin_name: Name of plugin to load
        plugin_dirs: Directories to search
        
    Returns:
        True if loaded successfully
    """
    with _plugin_lock:
        if plugin_name in _loaded_plugins:
            logger.info(f"Plugin {plugin_name} already loaded")
            return True
    
    # Find plugin directory
    plugin_path = None
    dirs = plugin_dirs or PLUGIN_DIRS
    
    for plugin_dir in dirs:
        # Check directory plugin
        dir_path = plugin_dir / plugin_name
        if dir_path.exists() and dir_path.is_dir():
            if (dir_path / "plugin.yaml").exists() or (dir_path / "__init__.py").exists():
                plugin_path = dir_path
                break
        
        # Check single-file plugin
        file_path = plugin_dir / f"{plugin_name}.py"
        if file_path.exists():
            plugin_path = file_path
            break
    
    if not plugin_path:
        logger.warning(f"Plugin {plugin_name} not found in {dirs}")
        return False
    
    try:
        # Load plugin module
        if plugin_path.is_dir():
            # Package plugin
            spec = importlib.util.spec_from_file_location(
                plugin_name,
                plugin_path / "__init__.py",
            )
        else:
            # Single file plugin
            spec = importlib.util.spec_from_file_location(
                plugin_name,
                plugin_path,
            )
        
        if not spec or not spec.loader:
            logger.error(f"Failed to create spec for {plugin_name}")
            return False
        
        module = importlib.util.module_from_spec(spec)
        
        # Add plugin directory to sys.path for imports
        if plugin_path.is_dir():
            sys.path.insert(0, str(plugin_path.parent))
        else:
            sys.path.insert(0, str(plugin_path.parent))
        
        # Execute module
        spec.loader.exec_module(module)
        
        # Call register function if exists
        if hasattr(module, "register"):
            ctx = PluginContext(plugin_name)
            module.register(ctx)
            logger.info(f"Plugin {plugin_name} registered {len(ctx.registered_tools)} tools")
        
        # Store loaded plugin
        with _plugin_lock:
            _loaded_plugins[plugin_name] = module
        
        return True
        
    except Exception as e:
        logger.exception(f"Failed to load plugin {plugin_name}")
        return False


def unload_plugin(plugin_name: str) -> bool:
    """Unload a plugin.
    
    Args:
        plugin_name: Name of plugin to unload
        
    Returns:
        True if unloaded successfully
    """
    with _plugin_lock:
        if plugin_name not in _loaded_plugins:
            return False
        
        # Unregister tools
        for tool_name in _plugin_tools.get(plugin_name, []):
            registry.unregister(tool_name)
        
        _plugin_tools.pop(plugin_name, None)
        _plugin_config.pop(plugin_name, None)
        _loaded_plugins.pop(plugin_name, None)
        
        logger.info(f"Plugin {plugin_name} unloaded")
        return True


def reload_plugin(plugin_name: str) -> bool:
    """Reload a plugin.
    
    Args:
        plugin_name: Name of plugin to reload
        
    Returns:
        True if reloaded successfully
    """
    unload_plugin(plugin_name)
    return load_plugin(plugin_name)


def get_loaded_plugins() -> List[str]:
    """Get list of loaded plugin names."""
    with _plugin_lock:
        return list(_loaded_plugins.keys())


def get_plugin_info(plugin_name: str) -> Optional[Dict]:
    """Get information about a loaded plugin."""
    with _plugin_lock:
        if plugin_name not in _loaded_plugins:
            return None
        
        return {
            "name": plugin_name,
            "tools": _plugin_tools.get(plugin_name, []),
            "config": _plugin_config.get(plugin_name, {}),
        }


def set_plugin_config(plugin_name: str, config: Dict) -> None:
    """Set plugin configuration."""
    with _plugin_lock:
        _plugin_config[plugin_name] = config


def get_plugin_config(plugin_name: str) -> Dict:
    """Get plugin configuration."""
    with _plugin_lock:
        return _plugin_config.get(plugin_name, {}).copy()


def plugin_load(
    plugin_name: str,
    plugin_dirs: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Load a plugin.
    
    Args:
        plugin_name: Name of plugin to load
        plugin_dirs: Optional custom plugin directories
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    dirs = [Path(d).expanduser() for d in plugin_dirs] if plugin_dirs else None
    success = load_plugin(plugin_name, dirs)
    
    return json.dumps({
        "success": success,
        "plugin": plugin_name,
        "loaded": get_loaded_plugins(),
    })


def plugin_unload(
    plugin_name: str,
    task_id: str = "default",
) -> str:
    """Unload a plugin."""
    success = unload_plugin(plugin_name)
    
    return json.dumps({
        "success": success,
        "plugin": plugin_name,
        "loaded": get_loaded_plugins(),
    })


def plugin_list(
    show_all: bool = False,
    task_id: str = "default",
) -> str:
    """List available and loaded plugins."""
    available = discover_plugins()
    loaded = get_loaded_plugins()
    
    result = {
        "available": available,
        "loaded": loaded,
        "plugin_dirs": [str(d) for d in PLUGIN_DIRS],
    }
    
    if show_all:
        # Include details for loaded plugins
        result["details"] = {
            name: get_plugin_info(name) for name in loaded
        }
    
    return json.dumps(result)


def plugin_reload(
    plugin_name: str,
    task_id: str = "default",
) -> str:
    """Reload a plugin."""
    success = reload_plugin(plugin_name)
    
    return json.dumps({
        "success": success,
        "plugin": plugin_name,
    })


def plugin_info(
    plugin_name: str,
    task_id: str = "default",
) -> str:
    """Get detailed plugin information."""
    info = get_plugin_info(plugin_name)
    
    if not info:
        return json.dumps({"error": f"Plugin {plugin_name} not loaded"})
    
    # Add available tools details
    tools_detail = []
    for tool_name in info["tools"]:
        tool_entry = registry.get(tool_name)
        if tool_entry:
            tools_detail.append({
                "name": tool_entry.name,
                "description": tool_entry.description,
                "toolset": tool_entry.toolset,
                "requires_env": tool_entry.requires_env,
            })
    
    info["tools_detail"] = tools_detail
    return json.dumps(info)


def plugin_config(
    action: str = "get",
    plugin_name: str = "",
    config: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Manage plugin configuration.
    
    Args:
        action: get, set, merge
        plugin_name: Plugin name
        config: Configuration dict (for set/merge)
        
    Returns:
        JSON string
    """
    if action == "get":
        return json.dumps(get_plugin_config(plugin_name))
    
    elif action == "set":
        if config is None:
            return json.dumps({"error": "config required for set action"})
        set_plugin_config(plugin_name, config)
        return json.dumps({"success": True, "config": get_plugin_config(plugin_name)})
    
    elif action == "merge":
        if config is None:
            return json.dumps({"error": "config required for merge action"})
        current = get_plugin_config(plugin_name)
        current.update(config)
        set_plugin_config(plugin_name, current)
        return json.dumps({"success": True, "config": get_plugin_config(plugin_name)})
    
    else:
        return json.dumps({"error": f"Unknown action: {action}"})


def auto_load_plugins(
    auto_discover: bool = True,
    plugin_dirs: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Auto-discover and load all available plugins."""
    dirs = [Path(d).expanduser() for d in plugin_dirs] if plugin_dirs else None
    available = discover_plugins(dirs)
    
    loaded = []
    failed = []
    
    for plugin in available:
        if load_plugin(plugin, dirs):
            loaded.append(plugin)
        else:
            failed.append(plugin)
    
    return json.dumps({
        "success": True,
        "discovered": available,
        "loaded": loaded,
        "failed": failed,
    })


def _register_plugin_system_tools():
    """Register plugin system tools."""
    tools = [
        ("plugin_load", plugin_load, "Load a plugin"),
        ("plugin_unload", plugin_unload, "Unload a plugin"),
        ("plugin_reload", plugin_reload, "Reload a plugin"),
        ("plugin_list", plugin_list, "List available and loaded plugins"),
        ("plugin_info", plugin_info, "Get detailed plugin information"),
        ("plugin_config", plugin_config, "Manage plugin configuration"),
        ("auto_load_plugins", auto_load_plugins, "Auto-discover and load all plugins"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="plugins",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_plugin_system_tools()