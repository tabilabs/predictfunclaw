from __future__ import annotations

import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .config import MANDATED_MCP_COMMAND_DEFAULT

MANDATED_MCP_NPM_PACKAGE = "@erc-mandated/mcp"


class MandatedMcpSetupError(RuntimeError):
    """Raised when mandated MCP setup fails."""


class MandatedMcpInstallPrerequisiteError(MandatedMcpSetupError):
    """Raised when a prerequisite such as npm is missing."""


class MandatedMcpInstallRuntimeError(MandatedMcpSetupError):
    """Raised when install completed unsuccessfully."""


@dataclass(frozen=True)
class MandatedMcpSetupResult:
    status: str
    command: str | None
    installed: bool
    wrote_env: bool
    message: str


def _merged_env(process_env: Mapping[str, str] | None = None) -> dict[str, str]:
    env = os.environ.copy()
    if process_env:
        env.update(process_env)
    return env


def _resolve_executable(
    command: str, process_env: Mapping[str, str] | None = None
) -> str | None:
    argv = shlex.split(command)
    if not argv:
        return None
    executable = argv[0]
    if "/" in executable:
        path = Path(executable).expanduser()
        if path.exists() and os.access(path, os.X_OK):
            return str(path)
        return None
    env = _merged_env(process_env)
    return shutil.which(executable, path=env.get("PATH"))


def detect_mandated_mcp_command(
    process_env: Mapping[str, str] | None = None,
) -> tuple[str | None, str | None]:
    explicit = (process_env or {}).get("ERC_MANDATED_MCP_COMMAND")
    if explicit and _resolve_executable(explicit, process_env):
        return explicit, "configured"

    if _resolve_executable(MANDATED_MCP_COMMAND_DEFAULT, process_env):
        return MANDATED_MCP_COMMAND_DEFAULT, "default"

    return None, None


def _write_env_var(env_path: Path, key: str, value: str) -> None:
    lines = env_path.read_text().splitlines() if env_path.exists() else []
    replacement = f"{key}={value}"
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith(f"{key}="):
            lines[index] = replacement
            replaced = True
            break
    if not replaced:
        lines.append(replacement)
    env_path.write_text("\n".join(lines).rstrip() + "\n")


def _install_via_npm(
    process_env: Mapping[str, str] | None = None,
) -> None:
    npm = _resolve_executable("npm", process_env)
    if npm is None:
        raise MandatedMcpInstallPrerequisiteError(
            "npm is required to install erc-mandated-mcp automatically. Install npm first, then re-run setup."
        )

    env = _merged_env(process_env)
    result = subprocess.run(
        [npm, "install", "-g", MANDATED_MCP_NPM_PACKAGE],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        stderr = (result.stderr or result.stdout or "").strip()
        raise MandatedMcpInstallRuntimeError(
            f"Failed to install {MANDATED_MCP_NPM_PACKAGE}: {stderr or 'unknown npm error'}"
        )


def configure_mandated_mcp(
    *,
    skill_dir: Path,
    process_env: Mapping[str, str] | None = None,
    install: bool = False,
    write_env: bool = False,
) -> MandatedMcpSetupResult:
    command, source = detect_mandated_mcp_command(process_env)
    installed = False

    if command is None:
        if not install:
            return MandatedMcpSetupResult(
                status="missing",
                command=None,
                installed=False,
                wrote_env=False,
                message=(
                    "No mandated-vault MCP launcher was found. Install erc-mandated-mcp and rerun this command, "
                    "or pass --install to let PredictClaw try npm install -g @erc-mandated/mcp."
                ),
            )

        _install_via_npm(process_env)
        installed = True
        command, source = detect_mandated_mcp_command(process_env)
        if command is None:
            raise MandatedMcpInstallRuntimeError(
                "Installed @erc-mandated/mcp, but could not resolve the erc-mandated-mcp launcher afterwards."
            )

    wrote_env = False
    if write_env and command is not None:
        _write_env_var(skill_dir / ".env", "ERC_MANDATED_MCP_COMMAND", command)
        wrote_env = True

    source_label = (
        "configured command" if source == "configured" else "default launcher"
    )
    return MandatedMcpSetupResult(
        status="ready",
        command=command,
        installed=installed,
        wrote_env=wrote_env,
        message=(
            f"Mandated MCP is ready via {source_label}: {command}."
            + (
                " PredictClaw updated .env with ERC_MANDATED_MCP_COMMAND."
                if wrote_env
                else ""
            )
        ),
    )
