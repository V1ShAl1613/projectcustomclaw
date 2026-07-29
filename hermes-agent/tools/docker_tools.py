#!/usr/bin/env python3
"""
Docker Integration Tools Module

Extends Hermes with comprehensive Docker operations:
- Build images
- Run containers
- Inspect containers/images/networks/volumes
- Read logs
- Docker Compose support
- Network inspection
- Volume management
- Image cleanup
- Resource monitoring
- Health monitoring
- Container restart/stop/remove
- Container statistics

All operations use the existing terminal tool infrastructure and
respect workspace boundaries.
"""

import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from tools.registry import registry
from tools.file_tools import _resolve_path_for_task, _get_file_ops
from tools.terminal_tool import terminal_tool

logger = logging.getLogger(__name__)


def _run_docker_command(
    command: str,
    task_id: str = "default",
    timeout: int = 120,
) -> Dict[str, Any]:
    """Run a docker command via terminal tool."""
    try:
        result = terminal_tool(
            command=command,
            task_id=task_id,
            timeout=timeout,
        )
        return json.loads(result)
    except Exception as e:
        logger.exception("Docker command failed: %s", e)
        return {"error": f"Docker command failed: {e}", "success": False}


def _resolve_context_path(path: str, task_id: str = "default") -> Path:
    """Resolve a context path for Docker operations."""
    return _resolve_path_for_task(path, task_id)


def docker_build(
    context: str = ".",
    dockerfile: Optional[str] = None,
    tag: Optional[str] = None,
    tags: Optional[List[str]] = None,
    build_args: Optional[Dict[str, str]] = None,
    target: Optional[str] = None,
    no_cache: bool = False,
    pull: bool = False,
    platform: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Build a Docker image."""
    try:
        context_path = _resolve_context_path(context, task_id)
        
        # Build command
        cmd_parts = ["docker", "build"]
        
        if dockerfile:
            cmd_parts.extend(["-f", dockerfile])
        
        # Handle tags
        if tag:
            cmd_parts.extend(["-t", tag])
        if tags:
            for t in tags:
                cmd_parts.extend(["-t", t])
        
        # Build args
        if build_args:
            for key, value in build_args.items():
                cmd_parts.extend(["--build-arg", f"{key}={value}"])
        
        if target:
            cmd_parts.extend(["--target", target])
        if no_cache:
            cmd_parts.append("--no-cache")
        if pull:
            cmd_parts.append("--pull")
        if platform:
            cmd_parts.extend(["--platform", platform])
        
        cmd_parts.append(str(context_path))
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id, timeout=600)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "image": tag or tags[0] if tags else "built",
                "context": str(context_path),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Build failed"),
            })
    
    except Exception as e:
        logger.exception("docker_build error: %s", e)
        return json.dumps({"error": f"Build failed: {e}"})


def docker_run(
    image: str,
    name: Optional[str] = None,
    command: Optional[str] = None,
    args: Optional[List[str]] = None,
    detach: bool = True,
    remove: bool = False,
    interactive: bool = False,
    tty: bool = False,
    ports: Optional[Dict[str, str]] = None,
    volumes: Optional[Dict[str, str]] = None,
    environment: Optional[Dict[str, str]] = None,
    env_file: Optional[str] = None,
    network: Optional[str] = None,
    restart: Optional[str] = None,
    cpus: Optional[float] = None,
    memory: Optional[str] = None,
    workdir: Optional[str] = None,
    user: Optional[str] = None,
    privileged: bool = False,
    cap_add: Optional[List[str]] = None,
    cap_drop: Optional[List[str]] = None,
    security_opt: Optional[List[str]] = None,
    labels: Optional[Dict[str, str]] = None,
    entrypoint: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Run a Docker container."""
    try:
        cmd_parts = ["docker", "run"]
        
        if detach:
            cmd_parts.append("-d")
        else:
            cmd_parts.append("--rm")
        
        if name:
            cmd_parts.extend(["--name", name])
        
        if remove:
            cmd_parts.append("--rm")
        
        if interactive:
            cmd_parts.append("-i")
        if tty:
            cmd_parts.append("-t")
        
        # Ports
        if ports:
            for host_port, container_port in ports.items():
                cmd_parts.extend(["-p", f"{host_port}:{container_port}"])
        
        # Volumes
        if volumes:
            for host_path, container_path in volumes.items():
                host_resolved = _resolve_context_path(host_path, task_id)
                cmd_parts.extend(["-v", f"{host_resolved}:{container_path}"])
        
        # Environment
        if environment:
            for key, value in environment.items():
                cmd_parts.extend(["-e", f"{key}={value}"])
        
        if env_file:
            env_path = _resolve_context_path(env_file, task_id)
            cmd_parts.extend(["--env-file", str(env_path)])
        
        if network:
            cmd_parts.extend(["--network", network])
        
        if restart:
            cmd_parts.extend(["--restart", restart])
        
        if cpus:
            cmd_parts.extend(["--cpus", str(cpus)])
        
        if memory:
            cmd_parts.extend(["--memory", memory])
        
        if workdir:
            cmd_parts.extend(["-w", workdir])
        
        if user:
            cmd_parts.extend(["-u", user])
        
        if privileged:
            cmd_parts.append("--privileged")
        
        if cap_add:
            for cap in cap_add:
                cmd_parts.extend(["--cap-add", cap])
        
        if cap_drop:
            for cap in cap_drop:
                cmd_parts.extend(["--cap-drop", cap])
        
        if security_opt:
            for opt in security_opt:
                cmd_parts.extend(["--security-opt", opt])
        
        if labels:
            for key, value in labels.items():
                cmd_parts.extend(["-l", f"{key}={value}"])
        
        if entrypoint:
            cmd_parts.extend(["--entrypoint", entrypoint])
        
        cmd_parts.append(image)
        
        if command:
            cmd_parts.append(command)
        if args:
            cmd_parts.extend(args)
        
        command_str = " ".join(cmd_parts)
        result = _run_docker_command(command_str, task_id, timeout=60)
        
        if result.get("success"):
            container_id = result.get("stdout", "").strip()
            return json.dumps({
                "success": True,
                "container_id": container_id,
                "name": name,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Run failed"),
            })
    
    except Exception as e:
        logger.exception("docker_run error: %s", e)
        return json.dumps({"error": f"Run failed: {e}"})


def docker_inspect(
    target: str,
    type: str = "container",  # container, image, network, volume
    format: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Inspect a Docker object."""
    try:
        cmd = f"docker inspect"
        if format:
            cmd += f" --format '{format}'"
        cmd += f" {target}"
        
        result = _run_docker_command(cmd, task_id)
        
        if result.get("success"):
            try:
                output = result.get("stdout", "").strip()
                if output:
                    return json.dumps({
                        "success": True,
                        "data": json.loads(output) if not format else output,
                    })
                return json.dumps({"success": True, "data": []})
            except json.JSONDecodeError:
                return json.dumps({"success": True, "data": output})
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Inspect failed"),
            })
    
    except Exception as e:
        logger.exception("docker_inspect error: %s", e)
        return json.dumps({"error": f"Inspect failed: {e}"})


def docker_logs(
    container: str,
    follow: bool = False,
    tail: Optional[int] = 100,
    since: Optional[str] = None,
    until: Optional[str] = None,
    timestamps: bool = False,
    task_id: str = "default",
) -> str:
    """Get container logs."""
    try:
        cmd_parts = ["docker", "logs"]
        
        if follow:
            cmd_parts.append("-f")
        if tail is not None:
            cmd_parts.extend(["--tail", str(tail)])
        if since:
            cmd_parts.extend(["--since", since])
        if until:
            cmd_parts.extend(["--until", until])
        if timestamps:
            cmd_parts.append("-t")
        
        cmd_parts.append(container)
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id, timeout=30 if not follow else 300)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "logs": result.get("stdout", ""),
                "stderr": result.get("stderr", ""),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Logs failed"),
            })
    
    except Exception as e:
        logger.exception("docker_logs error: %s", e)
        return json.dumps({"error": f"Logs failed: {e}"})


def docker_compose(
    action: str,  # up, down, ps, logs, build, pull, push, restart, stop, start, config
    project_dir: str = ".",
    project_name: Optional[str] = None,
    services: Optional[List[str]] = None,
    detach: bool = True,
    build: bool = False,
    force_recreate: bool = False,
    no_deps: bool = False,
    remove_orphans: bool = False,
    scale: Optional[Dict[str, int]] = None,
    timeout: int = 10,
    task_id: str = "default",
) -> str:
    """Run Docker Compose commands."""
    try:
        project_path = _resolve_context_path(project_dir, task_id)
        
        cmd_parts = ["docker", "compose"]
        
        if project_name:
            cmd_parts.extend(["-p", project_name])
        
        cmd_parts.append(action)
        
        if action == "up":
            if detach:
                cmd_parts.append("-d")
            if build:
                cmd_parts.append("--build")
            if force_recreate:
                cmd_parts.append("--force-recreate")
            if no_deps:
                cmd_parts.append("--no-deps")
            if remove_orphans:
                cmd_parts.append("--remove-orphans")
            if scale:
                for service, count in scale.items():
                    cmd_parts.extend(["--scale", f"{service}={count}"])
            if timeout:
                cmd_parts.extend(["--timeout", str(timeout)])
        
        elif action == "down":
            cmd_parts.extend(["-v", "--remove-orphans"])
        
        elif action == "logs":
            if tail:
                cmd_parts.extend(["--tail", str(tail)])
            if follow:
                cmd_parts.append("-f")
        
        if services:
            cmd_parts.extend(services)
        
        # Run in project directory
        full_command = f"cd {project_path} && " + " ".join(cmd_parts)
        result = _run_docker_command(full_command, task_id, timeout=300)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "output": result.get("stdout", ""),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", f"Compose {action} failed"),
            })
    
    except Exception as e:
        logger.exception("docker_compose error: %s", e)
        return json.dumps({"error": f"Compose failed: {e}"})


def docker_network(
    action: str,  # create, inspect, ls, rm, connect, disconnect
    name: Optional[str] = None,
    driver: str = "bridge",
    options: Optional[Dict[str, str]] = None,
    labels: Optional[Dict[str, str]] = None,
    container: Optional[str] = None,
    ip: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """Manage Docker networks."""
    try:
        cmd_parts = ["docker", "network", action]
        
        if action == "create":
            if not name:
                return json.dumps({"error": "Network name required for create"})
            cmd_parts.extend(["--driver", driver])
            if options:
                for key, value in options.items():
                    cmd_parts.extend(["-o", f"{key}={value}"])
            if labels:
                for key, value in labels.items():
                    cmd_parts.extend(["--label", f"{key}={value}"])
            cmd_parts.append(name)
        
        elif action == "inspect":
            if not name:
                return json.dumps({"error": "Network name required for inspect"})
            cmd_parts.append(name)
        
        elif action == "ls":
            cmd_parts.extend(["--format", "json"])
        
        elif action == "rm":
            if not name:
                return json.dumps({"error": "Network name required for rm"})
            cmd_parts.append(name)
        
        elif action in ("connect", "disconnect"):
            if not name or not container:
                return json.dumps({"error": "Network name and container required"})
            if ip:
                cmd_parts.extend(["--ip", ip])
            cmd_parts.extend([name, container])
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "output": result.get("stdout", ""),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", f"Network {action} failed"),
            })
    
    except Exception as e:
        logger.exception("docker_network error: %s", e)
        return json.dumps({"error": f"Network operation failed: {e}"})


def docker_volume(
    action: str,  # create, inspect, ls, rm, prune
    name: Optional[str] = None,
    driver: str = "local",
    options: Optional[Dict[str, str]] = None,
    labels: Optional[Dict[str, str]] = None,
    task_id: str = "default",
) -> str:
    """Manage Docker volumes."""
    try:
        cmd_parts = ["docker", "volume", action]
        
        if action == "create":
            if not name:
                return json.dumps({"error": "Volume name required for create"})
            cmd_parts.extend(["--driver", driver])
            if options:
                for key, value in options.items():
                    cmd_parts.extend(["-o", f"{key}={value}"])
            if labels:
                for key, value in labels.items():
                    cmd_parts.extend(["--label", f"{key}={value}"])
            cmd_parts.append(name)
        
        elif action == "inspect":
            if not name:
                return json.dumps({"error": "Volume name required for inspect"})
            cmd_parts.append(name)
        
        elif action == "ls":
            cmd_parts.extend(["--format", "json"])
        
        elif action == "rm":
            if not name:
                return json.dumps({"error": "Volume name required for rm"})
            cmd_parts.append(name)
        
        elif action == "prune":
            cmd_parts.append("-f")
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "output": result.get("stdout", ""),
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", f"Volume {action} failed"),
            })
    
    except Exception as e:
        logger.exception("docker_volume error: %s", e)
        return json.dumps({"error": f"Volume operation failed: {e}"})


def docker_cleanup(
    images: bool = True,
    containers: bool = True,
    volumes: bool = False,
    networks: bool = False,
    build_cache: bool = True,
    force: bool = False,
    task_id: str = "default",
) -> str:
    """Clean up Docker resources."""
    try:
        results = {}
        
        if containers:
            cmd = "docker container prune"
            if force:
                cmd += " -f"
            result = _run_docker_command(cmd, task_id)
            results["containers"] = "success" if result.get("success") else result.get("error")
        
        if images:
            cmd = "docker image prune -a"
            if force:
                cmd += " -f"
            result = _run_docker_command(cmd, task_id)
            results["images"] = "success" if result.get("success") else result.get("error")
        
        if volumes:
            cmd = "docker volume prune"
            if force:
                cmd += " -f"
            result = _run_docker_command(cmd, task_id)
            results["volumes"] = "success" if result.get("success") else result.get("error")
        
        if networks:
            cmd = "docker network prune"
            if force:
                cmd += " -f"
            result = _run_docker_command(cmd, task_id)
            results["networks"] = "success" if result.get("success") else result.get("error")
        
        if build_cache:
            cmd = "docker builder prune -a"
            if force:
                cmd += " -f"
            result = _run_docker_command(cmd, task_id)
            results["build_cache"] = "success" if result.get("success") else result.get("error")
        
        return json.dumps({
            "success": True,
            "results": results,
        })
    
    except Exception as e:
        logger.exception("docker_cleanup error: %s", e)
        return json.dumps({"error": f"Cleanup failed: {e}"})


def docker_monitor(
    container: Optional[str] = None,
    duration: int = 10,
    interval: float = 1.0,
    task_id: str = "default",
) -> str:
    """Monitor container resource usage."""
    try:
        cmd = "docker stats --no-stream --format 'json'"
        if container:
            cmd += f" {container}"
        
        result = _run_docker_command(cmd, task_id)
        
        if not result.get("success"):
            return json.dumps({
                "success": False,
                "error": result.get("error", "Stats failed"),
            })
        
        # Parse stats
        stats = []
        for line in result.get("stdout", "").strip().split('\n'):
            if line.strip():
                try:
                    stats.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        
        return json.dumps({
            "success": True,
            "stats": stats,
            "timestamp": time.time(),
        })
    
    except Exception as e:
        logger.exception("docker_monitor error: %s", e)
        return json.dumps({"error": f"Monitor failed: {e}"})


def docker_health(
    container: str,
    task_id: str = "default",
) -> str:
    """Check container health status."""
    try:
        # Get health status
        cmd = f"docker inspect --format '{{{{.State.Health.Status}}}}' {container}"
        result = _run_docker_command(cmd, task_id)
        
        if result.get("success"):
            health = result.get("stdout", "").strip()
            
            # Get more details
            details_cmd = f"docker inspect {container}"
            details_result = _run_docker_command(details_cmd, task_id)
            
            if details_result.get("success"):
                try:
                    details = json.loads(details_result.get("stdout", "[]"))
                    if details:
                        state = details[0].get("State", {})
                        health_info = state.get("Health", {})
                        
                        return json.dumps({
                            "success": True,
                            "container": container,
                            "status": state.get("Status"),
                            "health": health_info.get("Status", "none"),
                            "failing_streak": health_info.get("FailingStreak", 0),
                            "log": health_info.get("Log", [])[-5:] if health_info.get("Log") else [],
                        })
                except json.JSONDecodeError:
                    pass
            
            return json.dumps({
                "success": True,
                "container": container,
                "health": health,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Health check failed"),
            })
    
    except Exception as e:
        logger.exception("docker_health error: %s", e)
        return json.dumps({"error": f"Health check failed: {e}"})


def docker_restart(
    container: str,
    timeout: int = 10,
    task_id: str = "default",
) -> str:
    """Restart a container."""
    try:
        cmd = f"docker restart -t {timeout} {container}"
        result = _run_docker_command(cmd, task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "container": container,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Restart failed"),
            })
    
    except Exception as e:
        logger.exception("docker_restart error: %s", e)
        return json.dumps({"error": f"Restart failed: {e}"})


def docker_stop(
    container: str,
    timeout: int = 10,
    task_id: str = "default",
) -> str:
    """Stop a container."""
    try:
        cmd = f"docker stop -t {timeout} {container}"
        result = _run_docker_command(cmd, task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "container": container,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Stop failed"),
            })
    
    except Exception as e:
        logger.exception("docker_stop error: %s", e)
        return json.dumps({"error": f"Stop failed: {e}"})


def docker_remove(
    container: str,
    force: bool = False,
    volumes: bool = False,
    task_id: str = "default",
) -> str:
    """Remove a container."""
    try:
        cmd_parts = ["docker", "rm"]
        if force:
            cmd_parts.append("-f")
        if volumes:
            cmd_parts.append("-v")
        cmd_parts.append(container)
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id)
        
        if result.get("success"):
            return json.dumps({
                "success": True,
                "container": container,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Remove failed"),
            })
    
    except Exception as e:
        logger.exception("docker_remove error: %s", e)
        return json.dumps({"error": f"Remove failed: {e}"})


def docker_stats(
    container: Optional[str] = None,
    all_containers: bool = True,
    task_id: str = "default",
) -> str:
    """Get container statistics."""
    try:
        cmd = "docker stats --no-stream --format 'json'"
        if container:
            cmd += f" {container}"
        elif not all_containers:
            cmd += " --all"
        
        result = _run_docker_command(cmd, task_id)
        
        if result.get("success"):
            stats = []
            for line in result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    try:
                        stats.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            
            return json.dumps({
                "success": True,
                "stats": stats,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "Stats failed"),
            })
    
    except Exception as e:
        logger.exception("docker_stats error: %s", e)
        return json.dumps({"error": f"Stats failed: {e}"})


def docker_ps(
    all: bool = False,
    filter: Optional[Dict[str, str]] = None,
    format: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """List containers."""
    try:
        cmd_parts = ["docker", "ps"]
        if all:
            cmd_parts.append("-a")
        if filter:
            for key, value in filter.items():
                cmd_parts.extend(["--filter", f"{key}={value}"])
        if format:
            cmd_parts.extend(["--format", format])
        else:
            cmd_parts.extend(["--format", "json"])
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id)
        
        if result.get("success"):
            containers = []
            for line in result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    try:
                        containers.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            
            return json.dumps({
                "success": True,
                "containers": containers,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "List failed"),
            })
    
    except Exception as e:
        logger.exception("docker_ps error: %s", e)
        return json.dumps({"error": f"List failed: {e}"})


def docker_images(
    all: bool = False,
    filter: Optional[str] = None,
    format: Optional[str] = None,
    task_id: str = "default",
) -> str:
    """List images."""
    try:
        cmd_parts = ["docker", "images"]
        if all:
            cmd_parts.append("-a")
        if filter:
            cmd_parts.extend(["--filter", filter])
        if format:
            cmd_parts.extend(["--format", format])
        else:
            cmd_parts.extend(["--format", "json"])
        
        command = " ".join(cmd_parts)
        result = _run_docker_command(command, task_id)
        
        if result.get("success"):
            images = []
            for line in result.get("stdout", "").strip().split('\n'):
                if line.strip():
                    try:
                        images.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
            
            return json.dumps({
                "success": True,
                "images": images,
            })
        else:
            return json.dumps({
                "success": False,
                "error": result.get("error", "List failed"),
            })
    
    except Exception as e:
        logger.exception("docker_images error: %s", e)
        return json.dumps({"error": f"List failed: {e}"})


# Register all tools
def _register_docker_tools():
    """Register all Docker tools with the registry."""

    tools = [
        ("docker_build", "docker", {
            "name": "docker_build",
            "description": "Build a Docker image from a Dockerfile",
            "parameters": {
                "type": "object",
                "properties": {
                    "context": {"type": "string", "description": "Build context path", "default": "."},
                    "dockerfile": {"type": "string", "description": "Path to Dockerfile", "default": None},
                    "tag": {"type": "string", "description": "Image tag", "default": None},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Multiple tags", "default": None},
                    "build_args": {"type": "object", "description": "Build arguments", "default": None},
                    "target": {"type": "string", "description": "Target build stage", "default": None},
                    "no_cache": {"type": "boolean", "description": "Disable cache", "default": False},
                    "pull": {"type": "boolean", "description": "Pull base image", "default": False},
                    "platform": {"type": "string", "description": "Target platform", "default": None},
                },
                "required": [],
            },
        }, docker_build, None, [], False, "🏗️", None),

        ("docker_run", "docker", {
            "name": "docker_run",
            "description": "Run a Docker container",
            "parameters": {
                "type": "object",
                "properties": {
                    "image": {"type": "string", "description": "Image to run"},
                    "name": {"type": "string", "description": "Container name", "default": None},
                    "command": {"type": "string", "description": "Command to run", "default": None},
                    "args": {"type": "array", "items": {"type": "string"}, "description": "Command arguments", "default": None},
                    "detach": {"type": "boolean", "description": "Run in background", "default": True},
                    "remove": {"type": "boolean", "description": "Auto-remove on exit", "default": False},
                    "interactive": {"type": "boolean", "description": "Interactive mode", "default": False},
                    "tty": {"type": "boolean", "description": "Allocate TTY", "default": False},
                    "ports": {"type": "object", "description": "Port mappings (host:container)", "default": None},
                    "volumes": {"type": "object", "description": "Volume mounts (host:container)", "default": None},
                    "environment": {"type": "object", "description": "Environment variables", "default": None},
                    "env_file": {"type": "string", "description": "Environment file path", "default": None},
                    "network": {"type": "string", "description": "Network name", "default": None},
                    "restart": {"type": "string", "description": "Restart policy", "default": None},
                    "cpus": {"type": "number", "description": "CPU limit", "default": None},
                    "memory": {"type": "string", "description": "Memory limit", "default": None},
                    "workdir": {"type": "string", "description": "Working directory", "default": None},
                    "user": {"type": "string", "description": "User to run as", "default": None},
                    "privileged": {"type": "boolean", "description": "Privileged mode", "default": False},
                    "cap_add": {"type": "array", "items": {"type": "string"}, "description": "Capabilities to add", "default": None},
                    "cap_drop": {"type": "array", "items": {"type": "string"}, "description": "Capabilities to drop", "default": None},
                    "security_opt": {"type": "array", "items": {"type": "string"}, "description": "Security options", "default": None},
                    "labels": {"type": "object", "description": "Labels", "default": None},
                    "entrypoint": {"type": "string", "description": "Override entrypoint", "default": None},
                },
                "required": ["image"],
            },
        }, docker_run, None, [], False, "🚀", None),

        ("docker_inspect", "docker", {
            "name": "docker_inspect",
            "description": "Inspect a Docker object (container, image, network, volume)",
            "parameters": {
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Object name or ID"},
                    "type": {"type": "string", "enum": ["container", "image", "network", "volume"], "default": "container"},
                    "format": {"type": "string", "description": "Go template format", "default": None},
                },
                "required": ["target"],
            },
        }, docker_inspect, None, [], False, "🔍", None),

        ("docker_logs", "docker", {
            "name": "docker_logs",
            "description": "Get container logs",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                    "follow": {"type": "boolean", "description": "Follow logs", "default": False},
                    "tail": {"type": "integer", "description": "Lines from end", "default": 100},
                    "since": {"type": "string", "description": "Show logs since timestamp", "default": None},
                    "until": {"type": "string", "description": "Show logs until timestamp", "default": None},
                    "timestamps": {"type": "boolean", "description": "Show timestamps", "default": False},
                },
                "required": ["container"],
            },
        }, docker_logs, None, [], False, "📋", None),

        ("docker_compose", "docker", {
            "name": "docker_compose",
            "description": "Run Docker Compose commands",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["up", "down", "ps", "logs", "build", "pull", "push", "restart", "stop", "start", "config"], "description": "Compose action"},
                    "project_dir": {"type": "string", "description": "Project directory", "default": "."},
                    "project_name": {"type": "string", "description": "Project name", "default": None},
                    "services": {"type": "array", "items": {"type": "string"}, "description": "Specific services", "default": None},
                    "detach": {"type": "boolean", "description": "Detached mode", "default": True},
                    "build": {"type": "boolean", "description": "Build images", "default": False},
                    "force_recreate": {"type": "boolean", "description": "Force recreate", "default": False},
                    "no_deps": {"type": "boolean", "description": "No dependencies", "default": False},
                    "remove_orphans": {"type": "boolean", "description": "Remove orphan containers", "default": False},
                    "scale": {"type": "object", "description": "Scale services", "default": None},
                    "timeout": {"type": "integer", "description": "Timeout seconds", "default": 10},
                },
                "required": ["action"],
            },
        }, docker_compose, None, [], False, "🐙", None),

        ("docker_network", "docker", {
            "name": "docker_network",
            "description": "Manage Docker networks",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "inspect", "ls", "rm", "connect", "disconnect"]},
                    "name": {"type": "string", "description": "Network name", "default": None},
                    "driver": {"type": "string", "description": "Network driver", "default": "bridge"},
                    "options": {"type": "object", "description": "Driver options", "default": None},
                    "labels": {"type": "object", "description": "Labels", "default": None},
                    "container": {"type": "string", "description": "Container name", "default": None},
                    "ip": {"type": "string", "description": "IP address", "default": None},
                },
                "required": ["action"],
            },
        }, docker_network, None, [], False, "🌐", None),

        ("docker_volume", "docker", {
            "name": "docker_volume",
            "description": "Manage Docker volumes",
            "parameters": {
                "type": "object",
                "properties": {
                    "action": {"type": "string", "enum": ["create", "inspect", "ls", "rm", "prune"]},
                    "name": {"type": "string", "description": "Volume name", "default": None},
                    "driver": {"type": "string", "description": "Volume driver", "default": "local"},
                    "options": {"type": "object", "description": "Driver options", "default": None},
                    "labels": {"type": "object", "description": "Labels", "default": None},
                },
                "required": ["action"],
            },
        }, docker_volume, None, [], False, "💾", None),

        ("docker_cleanup", "docker", {
            "name": "docker_cleanup",
            "description": "Clean up Docker resources",
            "parameters": {
                "type": "object",
                "properties": {
                    "images": {"type": "boolean", "description": "Remove unused images", "default": True},
                    "containers": {"type": "boolean", "description": "Remove stopped containers", "default": True},
                    "volumes": {"type": "boolean", "description": "Remove unused volumes", "default": False},
                    "networks": {"type": "boolean", "description": "Remove unused networks", "default": False},
                    "build_cache": {"type": "boolean", "description": "Remove build cache", "default": True},
                    "force": {"type": "boolean", "description": "Force removal", "default": False},
                },
                "required": [],
            },
        }, docker_cleanup, None, [], False, "🧹", None),

        ("docker_monitor", "docker", {
            "name": "docker_monitor",
            "description": "Monitor container resource usage",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name", "default": None},
                    "duration": {"type": "integer", "description": "Monitor duration (seconds)", "default": 10},
                    "interval": {"type": "number", "description": "Sample interval (seconds)", "default": 1.0},
                },
                "required": [],
            },
        }, docker_monitor, None, [], False, "📊", None),

        ("docker_health", "docker", {
            "name": "docker_health",
            "description": "Check container health status",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                },
                "required": ["container"],
            },
        }, docker_health, None, [], False, "🏥", None),

        ("docker_restart", "docker", {
            "name": "docker_restart",
            "description": "Restart a container",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                    "timeout": {"type": "integer", "description": "Stop timeout", "default": 10},
                },
                "required": ["container"],
            },
        }, docker_restart, None, [], False, "🔄", None),

        ("docker_stop", "docker", {
            "name": "docker_stop",
            "description": "Stop a container",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                    "timeout": {"type": "integer", "description": "Stop timeout", "default": 10},
                },
                "required": ["container"],
            },
        }, docker_stop, None, [], False, "⏹️", None),

        ("docker_remove", "docker", {
            "name": "docker_remove",
            "description": "Remove a container",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name or ID"},
                    "force": {"type": "boolean", "description": "Force removal", "default": False},
                    "volumes": {"type": "boolean", "description": "Remove volumes", "default": False},
                },
                "required": ["container"],
            },
        }, docker_remove, None, [], False, "🗑️", None),

        ("docker_stats", "docker", {
            "name": "docker_stats",
            "description": "Get container statistics",
            "parameters": {
                "type": "object",
                "properties": {
                    "container": {"type": "string", "description": "Container name", "default": None},
                    "all_containers": {"type": "boolean", "description": "Include all containers", "default": True},
                },
                "required": [],
            },
        }, docker_stats, None, [], False, "📈", None),

        ("docker_ps", "docker", {
            "name": "docker_ps",
            "description": "List containers",
            "parameters": {
                "type": "object",
                "properties": {
                    "all": {"type": "boolean", "description": "Show all containers", "default": False},
                    "filter": {"type": "object", "description": "Filters", "default": None},
                    "format": {"type": "string", "description": "Output format", "default": None},
                },
                "required": [],
            },
        }, docker_ps, None, [], False, "📦", None),

        ("docker_images", "docker", {
            "name": "docker_images",
            "description": "List Docker images",
            "parameters": {
                "type": "object",
                "properties": {
                    "all": {"type": "boolean", "description": "Show all images", "default": False},
                    "filter": {"type": "string", "description": "Filter expression", "default": None},
                    "format": {"type": "string", "description": "Output format", "default": None},
                },
                "required": [],
            },
        }, docker_images, None, [], False, "🖼️", None),
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
_register_docker_tools()

__all__ = [
    "docker_build",
    "docker_run",
    "docker_inspect",
    "docker_logs",
    "docker_compose",
    "docker_network",
    "docker_volume",
    "docker_cleanup",
    "docker_monitor",
    "docker_health",
    "docker_restart",
    "docker_stop",
    "docker_remove",
    "docker_stats",
    "docker_ps",
    "docker_images",
]

if __name__ == "__main__":
    print("Docker tools loaded successfully")