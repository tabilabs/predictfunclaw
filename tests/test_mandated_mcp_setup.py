from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

from lib.mandated_mcp_setup import (
    MandatedMcpInstallPrerequisiteError,
    MandatedMcpInstallRuntimeError,
    configure_mandated_mcp,
)


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_detects_default_launcher_and_can_backfill_env(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "erc-mandated-mcp", "#!/bin/sh\nexit 0\n")

    env_path = tmp_path / ".env"
    env_path.write_text("PREDICT_ENV=testnet\n")

    result = configure_mandated_mcp(
        skill_dir=tmp_path,
        process_env={"PATH": str(bin_dir)},
        write_env=True,
    )

    assert result.status == "ready"
    assert result.command == "erc-mandated-mcp"
    assert result.installed is False
    assert result.wrote_env is True
    assert "ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp" in env_path.read_text()


def test_install_requires_npm_when_launcher_missing(tmp_path: Path) -> None:
    with pytest.raises(MandatedMcpInstallPrerequisiteError, match="npm"):
        configure_mandated_mcp(
            skill_dir=tmp_path,
            process_env={"PATH": ""},
            install=True,
        )


def test_install_runs_npm_and_backfills_detected_launcher(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    launcher = bin_dir / "erc-mandated-mcp"

    npm = bin_dir / "npm"
    write_executable(
        npm,
        "#!/bin/sh\n"
        f"cat > '{launcher}' <<'EOF'\n"
        "#!/bin/sh\n"
        "exit 0\n"
        "EOF\n"
        f"chmod +x '{launcher}'\n"
        "exit 0\n",
    )

    env_path = tmp_path / ".env"
    env_path.write_text("PREDICT_ENV=testnet\n")

    result = configure_mandated_mcp(
        skill_dir=tmp_path,
        process_env={"PATH": f"{bin_dir}{os.pathsep}{os.defpath}"},
        install=True,
        write_env=True,
    )

    assert result.status == "ready"
    assert result.command == "erc-mandated-mcp"
    assert result.installed is True
    assert result.wrote_env is True
    assert "ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp" in env_path.read_text()


def test_install_fails_when_launcher_still_missing_after_npm(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    npm = bin_dir / "npm"
    write_executable(npm, "#!/bin/sh\nexit 0\n")

    with pytest.raises(MandatedMcpInstallRuntimeError, match="erc-mandated-mcp"):
        configure_mandated_mcp(
            skill_dir=tmp_path,
            process_env={"PATH": str(bin_dir)},
            install=True,
        )
