"""
Detect whether this process is running on bare metal, in a Docker
container on Linux, or in a Docker container on macOS (Docker Desktop).

Usage:
    from util.runtime import get_runtime_environment, RuntimeEnvironment

    env = get_runtime_environment()
    if env is RuntimeEnvironment.DOCKER_MACOS:
        ...

Container detection (`/.dockerenv`, cgroup contents) is reliable. Telling
Docker Desktop for Mac apart from native Linux Docker is best-effort:
Docker Desktop runs containers inside a "linuxkit" branded Linux VM, so
uname always reports Linux from inside the container, but the kernel
release string carries the "linuxkit" tag that never shows up on a real
Linux host's kernel. That's what we key off of. Set DOCKER_HOST_OS=darwin
in the environment to bypass the heuristic if it's ever wrong on a given
host (Docker Desktop internals have changed before -- e.g. its bind-mount
filesystem type used to be osxfs/virtiofs and is now "fakeowner").
"""

import enum
import functools
import os
import platform


class RuntimeEnvironment(enum.Enum):
    HOST = "host"
    DOCKER_LINUX = "docker_linux"
    DOCKER_MACOS = "docker_macos"


def is_in_container() -> bool:
    """Return True if the current process is running inside a container."""
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", "rt") as f:
            contents = f.read()
    except OSError:
        return False
    return any(marker in contents for marker in ("docker", "containerd", "kubepods"))


def _kernel_indicates_docker_desktop() -> bool:
    """Best-effort check for Docker Desktop's linuxkit VM kernel."""
    override = os.getenv("DOCKER_HOST_OS", "").strip().lower()
    if override:
        return override in ("darwin", "mac", "macos")
    return "linuxkit" in platform.release().lower()


@functools.lru_cache(maxsize=1)
def get_runtime_environment() -> RuntimeEnvironment:
    """Return the RuntimeEnvironment this process is executing in."""
    if not is_in_container():
        return RuntimeEnvironment.HOST
    if _kernel_indicates_docker_desktop():
        return RuntimeEnvironment.DOCKER_MACOS
    return RuntimeEnvironment.DOCKER_LINUX


def is_host() -> bool:
    """Return True if running directly on a machine, outside any container."""
    return get_runtime_environment() is RuntimeEnvironment.HOST


def is_docker_linux() -> bool:
    """Return True if running in a container on native Linux Docker."""
    return get_runtime_environment() is RuntimeEnvironment.DOCKER_LINUX


def is_docker_macos() -> bool:
    """Return True if running in a container under Docker Desktop for Mac."""
    return get_runtime_environment() is RuntimeEnvironment.DOCKER_MACOS


def is_in_docker() -> bool:
    """Return True if running in a container, regardless of host OS."""
    return get_runtime_environment() is not RuntimeEnvironment.HOST


def get_hostname() -> str:
    """
    Return the hostname to use to reach a service running directly on the
    host machine (e.g. MySQL, Redis, or the IBKR gateway started outside
    Docker) from wherever this process is running.

    - HOST: "localhost" -- already running on the machine.
    - DOCKER_LINUX: "localhost" -- `network_mode: host` puts the container
      in the host's real network namespace, so localhost is the host.
    - DOCKER_MACOS: "host.docker.internal" -- Docker Desktop's `host`
      network mode only shares its internal linuxkit VM's namespace, not
      the Mac's, so localhost inside the container is the VM, not the Mac.
      Docker Desktop provides host.docker.internal to bridge that gap.
    """
    if get_runtime_environment() is RuntimeEnvironment.DOCKER_MACOS:
        return "host.docker.internal"
    return "localhost"
