from __future__ import annotations

import stat
from pathlib import Path

from lib.mandated_mcp_setup import configure_mandated_mcp


def write_executable(path: Path, content: str) -> None:
    path.write_text(content)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_detects_default_launcher_without_backfilling_env(tmp_path: Path) -> None:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    write_executable(bin_dir / "erc-mandated-mcp", "#!/bin/sh\nexit 0\n")

    result = configure_mandated_mcp(
        skill_dir=tmp_path,
        process_env={"PATH": str(bin_dir)},
    )

    assert result.status == "ready"
    assert result.command == "erc-mandated-mcp"
    assert result.installed is False
    assert result.wrote_env is False
    assert ".env" not in result.message


def test_missing_launcher_returns_manual_install_guidance(tmp_path: Path) -> None:
    result = configure_mandated_mcp(
        skill_dir=tmp_path,
        process_env={"PATH": ""},
    )

    assert result.status == "missing"
    assert result.command is None
    assert result.installed is False
    assert result.wrote_env is False
    assert "Install the external erc-mandated-mcp runtime yourself" in result.message
    assert "ERC_MANDATED_MCP_COMMAND" in result.message
