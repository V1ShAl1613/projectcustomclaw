#!/usr/bin/env python3
"""
Performance Optimization Tools Module

Provides performance monitoring and optimization:
- Parallel task execution
- Tool scheduling
- Memory usage optimization
- Container startup optimization
- Cache management
"""

import asyncio
import gc
import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from tools.registry import registry
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Thread pool for parallel execution
_thread_pool: Optional[ThreadPoolExecutor] = None
_thread_pool_lock = threading.Lock()
_max_workers = int(os.environ.get("HERMES_MAX_WORKERS", "4"))

# Cache for tool results
_tool_cache: Dict[str, Dict] = {}
_cache_lock = threading.Lock()
_cache_ttl = 300  # 5 minutes default


def _get_thread_pool() -> ThreadPoolExecutor:
    """Get or create thread pool."""
    global _thread_pool
    with _thread_pool_lock:
        if _thread_pool is None:
            _thread_pool = ThreadPoolExecutor(max_workers=_max_workers)
        return _thread_pool


def parallel_execute(
    tasks: List[Dict],
    max_workers: Optional[int] = None,
    timeout: int = 300,
    task_id: str = "default",
) -> str:
    """Execute multiple tasks in parallel.
    
    Args:
        tasks: List of task dicts with 'tool', 'args', optional 'toolset'
        max_workers: Maximum parallel workers
        timeout: Total timeout in seconds
        task_id: Task identifier
        
    Returns:
        JSON string with results
    """
    workers = max_workers or _max_workers
    pool = _get_thread_pool()
    
    results = {}
    futures = {}
    
    def run_task(task: Dict) -> Dict:
        tool_name = task.get("tool")
        args = task.get("args", {})
        toolset = task.get("toolset")
        
        if not tool_name:
            return {"error": "tool required"}
        
        # Import and call tool
        try:
            from tools.registry import registry
            entry = registry.get(tool_name)
            if not entry:
                return {"error": f"Tool {tool_name} not found"}
            
            # Call handler
            result = entry.handler(args, task_id=task_id)
            return json.loads(result) if isinstance(result, str) else result
        except Exception as e:
            return {"error": str(e)}
    
    # Submit tasks
    for i, task in enumerate(tasks):
        future = pool.submit(run_task, task)
        futures[future] = i
    
    # Collect results
    for future in as_completed(futures, timeout=timeout):
        idx = futures[future]
        try:
            results[str(idx)] = future.result()
        except Exception as e:
            results[str(idx)] = {"error": str(e)}
    
    return json.dumps({
        "success": True,
        "results": results,
        "completed": len(results),
        "total": len(tasks),
    })


def tool_scheduler(
    action: str = "submit",
    tool: Optional[str] = None,
    args: Optional[Dict] = None,
    priority: int = 0,
    task_id: str = "default",
) -> str:
    """Schedule tool execution with priority.
    
    Args:
        action: submit, cancel, status, queue
        tool: Tool name
        args: Tool arguments
        priority: Priority (higher = more urgent)
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    # This would integrate with a proper task queue
    # For now, execute immediately
    if action == "submit":
        if not tool:
            return json.dumps({"error": "tool required"})
        
        try:
            from tools.registry import registry
            entry = registry.get(tool)
            if not entry:
                return json.dumps({"error": f"Tool {tool} not found"})
            
            result = entry.handler(args or {}, task_id=task_id)
            return json.dumps({"success": True, "result": json.loads(result)})
        except Exception as e:
            return json.dumps({"error": str(e)})
    
    return json.dumps({"error": f"Action {action} not implemented"})


def memory_optimize(
    action: str = "collect",
    threshold: int = 70,
    task_id: str = "default",
) -> str:
    """Optimize memory usage.
    
    Args:
        action: collect, stats, trim
        threshold: Memory percentage threshold for auto-trim
        task_id: Task identifier
        
    Returns:
        JSON string with memory stats
    """
    if action == "collect":
        collected = gc.collect()
        return json.dumps({"success": True, "collected": collected})
    
    elif action == "stats":
        import psutil
        process = psutil.Process()
        mem = process.memory_info()
        system = psutil.virtual_memory()
        
        return json.dumps({
            "process_mb": mem.rss / (1024 * 1024),
            "process_percent": process.memory_percent(),
            "system_percent": system.percent,
            "system_available_gb": system.available / (1024 ** 3),
        })
    
    elif action == "trim":
        import psutil
        process = psutil.Process()
        before = process.memory_info().rss
        gc.collect()
        # Try to release memory back to OS
        if hasattr(gc, "freeze"):
            gc.freeze()
        after = process.memory_info().rss
        return json.dumps({
            "success": True,
            "freed_mb": (before - after) / (1024 * 1024),
        })
    
    return json.dumps({"error": f"Unknown action: {action}"})


def container_startup_optimize(
    action: str = "prepull",
    images: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Optimize container startup time.
    
    Args:
        action: prepull, warmup, cleanup
        images: Images to prepull/warmup
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    if action == "prepull":
        if not images:
            return json.dumps({"error": "images required for prepull"})
        
        results = {}
        for img in images:
            cmd = f"docker pull {img}"
            result = terminal_tool(command=cmd, timeout=300, task_id=task_id)
            results[img] = json.loads(result)
        
        return json.dumps({"success": True, "results": results})
    
    elif action == "warmup":
        # Start and stop containers to warm up
        if not images:
            return json.dumps({"error": "images required for warmup"})
        
        results = {}
        for img in images:
            # Start container briefly
            cmd = f"docker run --rm {img} echo warmup"
            result = terminal_tool(command=cmd, timeout=60, task_id=task_id)
            results[img] = json.loads(result)
        
        return json.dumps({"success": True, "results": results})
    
    elif action == "cleanup":
        # Remove unused images
        cmd = "docker image prune -f"
        result = terminal_tool(command=cmd, timeout=120, task_id=task_id)
        return result
    
    return json.dumps({"error": f"Unknown action: {action}"})


def cache_manage(
    action: str = "stats",
    key: Optional[str] = None,
    value: Optional[Any] = None,
    ttl: int = 300,
    task_id: str = "default",
) -> str:
    """Manage tool result cache.
    
    Args:
        action: get, set, delete, clear, stats
        key: Cache key
        value: Value to cache
        ttl: Time to live in seconds
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    with _cache_lock:
        if action == "get":
            if not key:
                return json.dumps({"error": "key required"})
            
            entry = _tool_cache.get(key)
            if not entry:
                return json.dumps({"found": False})
            
            if time.time() - entry["timestamp"] > entry["ttl"]:
                _tool_cache.pop(key, None)
                return json.dumps({"found": False, "expired": True})
            
            return json.dumps({"found": True, "value": entry["value"]})
        
        elif action == "set":
            if not key or value is None:
                return json.dumps({"error": "key and value required"})
            
            _tool_cache[key] = {
                "value": value,
                "timestamp": time.time(),
                "ttl": ttl,
            }
            return json.dumps({"success": True})
        
        elif action == "delete":
            if not key:
                return json.dumps({"error": "key required"})
            _tool_cache.pop(key, None)
            return json.dumps({"success": True})
        
        elif action == "clear":
            _tool_cache.clear()
            return json.dumps({"success": True, "cleared": True})
        
        elif action == "stats":
            now = time.time()
            valid = sum(1 for e in _tool_cache.values() if now - e["timestamp"] < e["ttl"])
            expired = len(_tool_cache) - valid
            return json.dumps({
                "total": len(_tool_cache),
                "valid": valid,
                "expired": expired,
            })
        
        else:
            return json.dumps({"error": f"Unknown action: {action}"})


def profile_tool(
    tool: str,
    args: Dict,
    iterations: int = 10,
    task_id: str = "default",
) -> str:
    """Profile tool execution time.
    
    Args:
        tool: Tool name
        args: Tool arguments
        iterations: Number of iterations
        task_id: Task identifier
        
    Returns:
        JSON string with timing stats
    """
    try:
        from tools.registry import registry
        entry = registry.get(tool)
        if not entry:
            return json.dumps({"error": f"Tool {tool} not found"})
        
        times = []
        for _ in range(iterations):
            start = time.perf_counter()
            result = entry.handler(args, task_id=task_id)
            end = time.perf_counter()
            times.append(end - start)
        
        times.sort()
        return json.dumps({
            "success": True,
            "tool": tool,
            "iterations": iterations,
            "min_ms": times[0] * 1000,
            "max_ms": times[-1] * 1000,
            "avg_ms": sum(times) / len(times) * 1000,
            "median_ms": times[len(times) // 2] * 1000,
            "p95_ms": times[int(len(times) * 0.95)] * 1000,
            "p99_ms": times[int(len(times) * 0.99)] * 1000,
        })
    except Exception as e:
        return json.dumps({"error": str(e)})


def async_batch(
    operations: List[Dict],
    concurrency: int = 10,
    task_id: str = "default",
) -> str:
    """Execute batch of async operations.
    
    Args:
        operations: List of operation dicts
        concurrency: Max concurrent operations
        task_id: Task identifier
        
    Returns:
        JSON string with results
    """
    # This would use asyncio for true async
    # For now, use thread pool
    return parallel_execute(operations, max_workers=concurrency, task_id=task_id)


def resource_quota(
    action: str = "check",
    resource: str = "cpu",
    limit: Optional[float] = None,
    task_id: str = "default",
) -> str:
    """Manage resource quotas.
    
    Args:
        action: check, set, get
        resource: cpu, memory, disk, network
        limit: Limit value
        task_id: Task identifier
        
    Returns:
        JSON string with quota info
    """
    import psutil
    
    if action == "check":
        quotas = {}
        
        if resource in ("cpu", "all"):
            quotas["cpu"] = {
                "current_percent": psutil.cpu_percent(),
                "count": psutil.cpu_count(),
            }
        
        if resource in ("memory", "all"):
            mem = psutil.virtual_memory()
            quotas["memory"] = {
                "current_percent": mem.percent,
                "total_gb": mem.total / (1024 ** 3),
                "available_gb": mem.available / (1024 ** 3),
            }
        
        if resource in ("disk", "all"):
            disk = psutil.disk_usage("/")
            quotas["disk"] = {
                "current_percent": disk.percent,
                "total_gb": disk.total / (1024 ** 3),
                "free_gb": disk.free / (1024 ** 3),
            }
        
        return json.dumps({"success": True, "quotas": quotas})
    
    return json.dumps({"error": f"Action {action} not implemented"})


def _register_performance_tools():
    """Register performance tools."""
    tools = [
        ("parallel_execute", parallel_execute, "Execute multiple tasks in parallel"),
        ("tool_scheduler", tool_scheduler, "Schedule tool execution with priority"),
        ("memory_optimize", memory_optimize, "Optimize memory usage"),
        ("container_startup_optimize", container_startup_optimize, "Optimize container startup"),
        ("cache_manage", cache_manage, "Manage tool result cache"),
        ("profile_tool", profile_tool, "Profile tool execution time"),
        ("async_batch", async_batch, "Execute batch of async operations"),
        ("resource_quota", resource_quota, "Check resource quotas"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="performance",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: True,
            description=desc,
        )


_register_performance_tools()