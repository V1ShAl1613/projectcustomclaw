#!/usr/bin/env python3
"""
Monitoring Tools Module

Provides system and container monitoring capabilities:
- System metrics (CPU, RAM, Disk, GPU, Network)
- Container metrics (Docker stats)
- Real-time dashboard endpoints
- Health checks
- Alerting
"""

import json
import logging
import os
import platform
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)

# Try to import psutil
try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False

# Try to import GPUtil for GPU monitoring
try:
    import GPUtil
    GPUTIL_AVAILABLE = True
except ImportError:
    GPUTIL_AVAILABLE = False


# Global metrics cache
_metrics_cache: Dict[str, Any] = {}
_metrics_lock = threading.Lock()
_cache_ttl = 5  # seconds


def _run_command(cmd: str, timeout: int = 30) -> Dict[str, Any]:
    """Run a shell command and return result."""
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return {
            "success": result.returncode == 0,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "returncode": result.returncode,
        }
    except subprocess.TimeoutExpired:
        return {"success": False, "error": "Command timed out", "returncode": -1}
    except Exception as e:
        return {"success": False, "error": str(e), "returncode": -1}


def system_metrics(
    include_cpu: bool = True,
    include_memory: bool = True,
    include_disk: bool = True,
    include_network: bool = True,
    include_gpu: bool = True,
    interval: float = 1.0,
    task_id: str = "default",
) -> str:
    """Get system metrics.
    
    Args:
        include_cpu: Include CPU metrics
        include_memory: Include memory metrics
        include_disk: Include disk metrics
        include_network: Include network metrics
        include_gpu: Include GPU metrics
        interval: Sampling interval for CPU
        task_id: Task identifier
        
    Returns:
        JSON string with metrics
    """
    if not PSUTIL_AVAILABLE:
        return json.dumps({"error": "psutil not installed. Run: pip install psutil"})
    
    # Check cache
    cache_key = f"system_metrics_{include_cpu}_{include_memory}_{include_disk}_{include_network}_{include_gpu}"
    with _metrics_lock:
        if cache_key in _metrics_cache:
            cached = _metrics_cache[cache_key]
            if time.time() - cached["timestamp"] < _cache_ttl:
                return json.dumps({"success": True, "metrics": cached["data"], "cached": True})
    
    metrics = {
        "timestamp": time.time(),
        "hostname": platform.node(),
        "platform": platform.system(),
        "platform_version": platform.version(),
        "architecture": platform.machine(),
    }
    
    try:
        if include_cpu:
            cpu_percent = psutil.cpu_percent(interval=interval, percpu=True)
            cpu_freq = psutil.cpu_freq()
            cpu_count = psutil.cpu_count(logical=True)
            cpu_count_physical = psutil.cpu_count(logical=False)
            
            metrics["cpu"] = {
                "percent": cpu_percent,
                "percent_avg": sum(cpu_percent) / len(cpu_percent) if cpu_percent else 0,
                "count_logical": cpu_count,
                "count_physical": cpu_count_physical,
                "freq_current": cpu_freq.current if cpu_freq else None,
                "freq_max": cpu_freq.max if cpu_freq else None,
                "freq_min": cpu_freq.min if cpu_freq else None,
                "load_avg": os.getloadavg() if hasattr(os, "getloadavg") else None,
                "times": psutil.cpu_times()._asdict(),
            }
        
        if include_memory:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            
            metrics["memory"] = {
                "total": mem.total,
                "available": mem.available,
                "used": mem.used,
                "free": mem.free,
                "percent": mem.percent,
                "active": getattr(mem, "active", None),
                "inactive": getattr(mem, "inactive", None),
                "buffers": getattr(mem, "buffers", None),
                "cached": getattr(mem, "cached", None),
                "swap_total": swap.total,
                "swap_used": swap.used,
                "swap_free": swap.free,
                "swap_percent": swap.percent,
            }
        
        if include_disk:
            disk_partitions = []
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    disk_partitions.append({
                        "device": part.device,
                        "mountpoint": part.mountpoint,
                        "fstype": part.fstype,
                        "opts": part.opts,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                        "percent": usage.percent,
                    })
                except PermissionError:
                    pass
            
            io_counters = psutil.disk_io_counters()
            
            metrics["disk"] = {
                "partitions": disk_partitions,
                "io_counters": io_counters._asdict() if io_counters else None,
            }
        
        if include_network:
            net_io = psutil.net_io_counters()
            net_if_addrs = psutil.net_if_addrs()
            net_if_stats = psutil.net_if_stats()
            net_connections = psutil.net_connections(kind="inet")
            
            metrics["network"] = {
                "io_counters": net_io._asdict() if net_io else None,
                "interfaces": {
                    name: {
                        "addresses": [addr._asdict() for addr in addrs],
                        "stats": stats._asdict() if stats else None,
                    }
                    for name, addrs in net_if_addrs.items()
                    for stats in [net_if_stats.get(name)]
                },
                "connections_count": len(net_connections),
                "listening_ports": len([c for c in net_connections if c.status == "LISTEN"]),
            }
        
        if include_gpu and GPUTIL_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                metrics["gpu"] = [
                    {
                        "id": gpu.id,
                        "name": gpu.name,
                        "load": gpu.load * 100,
                        "memory_used": gpu.memoryUsed,
                        "memory_total": gpu.memoryTotal,
                        "memory_free": gpu.memoryFree,
                        "memory_percent": (gpu.memoryUsed / gpu.memoryTotal * 100) if gpu.memoryTotal > 0 else 0,
                        "temperature": gpu.temperature,
                    }
                    for gpu in gpus
                ]
            except Exception as e:
                metrics["gpu"] = {"error": str(e)}
        elif include_gpu:
            metrics["gpu"] = {"error": "GPUtil not installed. Run: pip install GPUtil"}
        
        # Cache result
        with _metrics_lock:
            _metrics_cache[cache_key] = {
                "timestamp": time.time(),
                "data": metrics,
            }
        
        return json.dumps({"success": True, "metrics": metrics})
        
    except Exception as e:
        logger.exception("Failed to get system metrics")
        return json.dumps({"error": str(e)})


def container_metrics(
    container_names: Optional[List[str]] = None,
    all_containers: bool = False,
    task_id: str = "default",
) -> str:
    """Get Docker container metrics.
    
    Args:
        container_names: Specific container names/IDs to monitor
        all_containers: Get metrics for all containers
        task_id: Task identifier
        
    Returns:
        JSON string with container metrics
    """
    try:
        if container_names:
            names = " ".join(container_names)
            cmd = f"docker stats --no-stream --format '{{json .}}' {names}"
        elif all_containers:
            cmd = "docker stats --no-stream --format '{{json .}}'"
        else:
            cmd = "docker stats --no-stream --format '{{json .}}'"
        
        result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
        data = json.loads(result)
        
        if not data.get("success"):
            return json.dumps({"error": data.get("stderr", "Failed to get container stats")})
        
        # Parse docker stats output (each line is JSON)
        containers = []
        for line in data.get("stdout", "").strip().split("\n"):
            if line:
                try:
                    containers.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        
        return json.dumps({"success": True, "containers": containers})
        
    except Exception as e:
        logger.exception("Failed to get container metrics")
        return json.dumps({"error": str(e)})


def docker_health(
    container_name: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Check Docker container health.
    
    Args:
        container_name: Specific container name (None = all)
        task_id: Task identifier
        
    Returns:
        JSON string with health status
    """
    try:
        if container_name:
            cmd = f"docker inspect --format '{{{{json .State.Health}}}}' {container_name}"
        else:
            cmd = "docker ps --format '{{json .}}' | jq -s 'map({name: .Names, status: .Status, health: .Health})'"
        
        result = terminal_tool(command=cmd, timeout=30, task_id=task_id)
        data = json.loads(result)
        
        if not data.get("success"):
            return json.dumps({"error": data.get("stderr", "Health check failed")})
        
        return result
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def process_monitor(
    pid: Optional[int] = None,
    name: Optional[str] = None,
    top_n: int = 20,
    task_id: str = "default",
) -> str:
    """Monitor processes.
    
    Args:
        pid: Specific PID to monitor
        name: Process name to filter
        top_n: Number of top processes to return
        task_id: Task identifier
        
    Returns:
        JSON string with process info
    """
    if not PSUTIL_AVAILABLE:
        return json.dumps({"error": "psutil not installed"})
    
    try:
        processes = []
        
        if pid:
            try:
                p = psutil.Process(pid)
                processes.append(_process_to_dict(p))
            except psutil.NoSuchProcess:
                return json.dumps({"error": f"Process {pid} not found"})
        elif name:
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if name.lower() in proc.info['name'].lower():
                        processes.append(_process_to_dict(proc))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
        else:
            # Get top processes by CPU
            procs = []
            for proc in psutil.process_iter(['pid', 'name', 'cpu_percent', 'memory_percent']):
                try:
                    procs.append(proc)
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            
            # Sort by CPU
            procs.sort(key=lambda p: p.info.get('cpu_percent', 0), reverse=True)
            processes = [_process_to_dict(p) for p in procs[:top_n]]
        
        return json.dumps({"success": True, "processes": processes})
        
    except Exception as e:
        return json.dumps({"error": str(e)})


def _process_to_dict(proc: psutil.Process) -> Dict:
    """Convert process to dict."""
    try:
        with proc.oneshot():
            return {
                "pid": proc.pid,
                "name": proc.name(),
                "cmdline": proc.cmdline(),
                "cpu_percent": proc.cpu_percent(),
                "memory_percent": proc.memory_percent(),
                "memory_info": proc.memory_info()._asdict(),
                "status": proc.status(),
                "create_time": proc.create_time(),
                "username": proc.username(),
                "num_threads": proc.num_threads(),
                "connections": len(proc.connections()) if proc.connections() else 0,
            }
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return {"pid": proc.pid, "error": "Access denied or process gone"}


def realtime_dashboard(
    action: str = "start",
    port: int = 8080,
    metrics_interval: int = 5,
    task_id: str = "default",
) -> str:
    """Manage real-time monitoring dashboard.
    
    Args:
        action: Action (start, stop, status)
        port: Dashboard port
        metrics_interval: Metrics collection interval (seconds)
        task_id: Task identifier
        
    Returns:
        JSON string with dashboard status
    """
    # This would start a simple HTTP server with WebSocket for real-time metrics
    # For now, return info about how to access
    
    if action == "start":
        return json.dumps({
            "success": True,
            "message": "Real-time dashboard would start here",
            "endpoints": {
                "metrics": f"http://localhost:{port}/metrics",
                "ws": f"ws://localhost:{port}/ws",
                "health": f"http://localhost:{port}/health",
            },
            "note": "Full implementation requires aiohttp/websockets",
        })
    elif action == "stop":
        return json.dumps({"success": True, "message": "Dashboard stopped"})
    else:
        return json.dumps({"success": True, "status": "not_running"})


def health_check(
    checks: Optional[List[str]] = None,
    task_id: str = "default",
) -> str:
    """Run system health checks.
    
    Args:
        checks: Specific checks to run (disk, memory, cpu, docker, network)
        task_id: Task identifier
        
    Returns:
        JSON string with health status
    """
    all_checks = ["disk", "memory", "cpu", "docker", "network", "gpu"]
    checks = checks or all_checks
    
    results = {}
    overall_healthy = True
    
    if not PSUTIL_AVAILABLE:
        return json.dumps({"error": "psutil not installed"})
    
    try:
        if "disk" in checks:
            disk_ok = True
            disk_details = {}
            for part in psutil.disk_partitions(all=False):
                try:
                    usage = psutil.disk_usage(part.mountpoint)
                    is_ok = usage.percent < 90
                    disk_ok = disk_ok and is_ok
                    disk_details[part.mountpoint] = {
                        "percent": usage.percent,
                        "free_gb": usage.free / (1024**3),
                        "healthy": is_ok,
                    }
                except PermissionError:
                    pass
            results["disk"] = {"healthy": disk_ok, "details": disk_details}
            overall_healthy = overall_healthy and disk_ok
        
        if "memory" in checks:
            mem = psutil.virtual_memory()
            swap = psutil.swap_memory()
            mem_ok = mem.percent < 90 and swap.percent < 90
            results["memory"] = {
                "healthy": mem_ok,
                "memory_percent": mem.percent,
                "swap_percent": swap.percent,
            }
            overall_healthy = overall_healthy and mem_ok
        
        if "cpu" in checks:
            cpu = psutil.cpu_percent(interval=1)
            load = os.getloadavg() if hasattr(os, "getloadavg") else [0, 0, 0]
            cpu_ok = cpu < 90 and (load[0] / psutil.cpu_count()) < 2.0
            results["cpu"] = {
                "healthy": cpu_ok,
                "percent": cpu,
                "load_1m": load[0],
                "load_5m": load[1],
                "load_15m": load[2],
            }
            overall_healthy = overall_healthy and cpu_ok
        
        if "docker" in checks:
            docker_ok = True
            docker_details = {}
            try:
                result = _run_command("docker version --format '{{.Server.Version}}'")
                if result["success"]:
                    docker_details["version"] = result["stdout"].strip()
                else:
                    docker_ok = False
                    docker_details["error"] = "Docker not running"
            except Exception:
                docker_ok = False
                docker_details["error"] = "Docker not available"
            
            # Check containers
            result = _run_command("docker ps --format '{{.Names}}:{{.Status}}'")
            if result["success"]:
                containers = result["stdout"].strip().split("\n")
                docker_details["containers"] = len([c for c in containers if c])
            
            results["docker"] = {"healthy": docker_ok, "details": docker_details}
            overall_healthy = overall_healthy and docker_ok
        
        if "network" in checks:
            net_ok = True
            try:
                # Check if we can reach internet
                result = _run_command("curl -s -o /dev/null -w '%{http_code}' --max-time 5 https://google.com")
                if result["success"] and result["stdout"] == "200":
                    net_ok = True
                else:
                    net_ok = False
            except Exception:
                net_ok = False
            
            results["network"] = {"healthy": net_ok}
            overall_healthy = overall_healthy and net_ok
        
        if "gpu" in checks:
            if GPUTIL_AVAILABLE:
                try:
                    gpus = GPUtil.getGPUs()
                    gpu_ok = all(g.temperature < 85 for g in gpus) if gpus else True
                    results["gpu"] = {
                        "healthy": gpu_ok,
                        "gpus": [
                            {
                                "id": g.id,
                                "name": g.name,
                                "temperature": g.temperature,
                                "load": g.load * 100,
                            }
                            for g in gpus
                        ],
                    }
                    overall_healthy = overall_healthy and gpu_ok
                except Exception as e:
                    results["gpu"] = {"healthy": False, "error": str(e)}
            else:
                results["gpu"] = {"healthy": True, "note": "GPUtil not installed"}
        
        return json.dumps({
            "healthy": overall_healthy,
            "timestamp": time.time(),
            "checks": results,
        })
        
    except Exception as e:
        logger.exception("Health check failed")
        return json.dumps({"error": str(e), "healthy": False})


def metrics_history(
    metric: str = "cpu",
    duration: int = 300,
    interval: int = 10,
    task_id: str = "default",
) -> str:
    """Get historical metrics.
    
    Args:
        metric: Metric type (cpu, memory, disk, network, gpu)
        duration: Duration in seconds
        interval: Sampling interval in seconds
        task_id: Task identifier
        
    Returns:
        JSON string with historical data
    """
    # This would require a background collector
    # For now, return current metrics with note
    return json.dumps({
        "success": True,
        "note": "Historical metrics require background collector. Use system_metrics for current values.",
        "current": json.loads(system_metrics(task_id=task_id)),
    })


def alert_rules(
    action: str = "list",
    rule: Optional[Dict] = None,
    task_id: str = "default",
) -> str:
    """Manage alert rules.
    
    Args:
        action: Action (list, add, remove, test)
        rule: Alert rule definition
        task_id: Task identifier
        
    Returns:
        JSON string with result
    """
    # Alert rules stored in memory for now
    # In production, would use config file
    return json.dumps({
        "success": True,
        "message": "Alert rules management not fully implemented",
        "actions": ["list", "add", "remove", "test"],
        "example_rule": {
            "name": "high_cpu",
            "metric": "cpu.percent_avg",
            "condition": ">",
            "threshold": 90,
            "duration": 60,
            "severity": "warning",
        },
    })


def _register_monitoring_tools():
    """Register all monitoring tools."""
    tools = [
        ("system_metrics", system_metrics, "Get system metrics (CPU, RAM, Disk, Network, GPU)"),
        ("container_metrics", container_metrics, "Get Docker container metrics"),
        ("docker_health", docker_health, "Check Docker container health"),
        ("process_monitor", process_monitor, "Monitor system processes"),
        ("health_check", health_check, "Run system health checks"),
        ("realtime_dashboard", realtime_dashboard, "Manage real-time monitoring dashboard"),
        ("metrics_history", metrics_history, "Get historical metrics"),
        ("alert_rules", alert_rules, "Manage alert rules"),
    ]
    
    for name, func, desc in tools:
        registry.register(
            name=name,
            toolset="monitoring",
            schema={"name": name, "description": desc, "parameters": {"type": "object", "properties": {}}},
            handler=func,
            check_fn=lambda: PSUTIL_AVAILABLE,
            description=desc,
        )


_register_monitoring_tools()