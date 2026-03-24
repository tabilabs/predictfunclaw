from __future__ import annotations

from pathlib import Path

from lib.env_backfill import backfill_env_file


def read_env_map(env_path: Path) -> dict[str, str]:
    payload: dict[str, str] = {}
    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        payload[key] = value
    return payload


def test_backfill_env_file_updates_bootstrap_env_without_touching_unrelated_values(
    tmp_path: Path,
) -> None:
    env_path = tmp_path / ".env"
    env_path.write_text(
        "\n".join(
            [
                "PREDICT_ENV=testnet",
                "PREDICT_WALLET_MODE=mandated-vault",
                "PREDICT_EOA_PRIVATE_KEY=0xbootstrap-signer",
                "ERC_MANDATED_MCP_COMMAND=erc-mandated-mcp",
                "OPENROUTER_API_KEY=leave-me-alone",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    backfill_env_file(
        env_path,
        {
            "ERC_MANDATED_VAULT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6",
            "ERC_MANDATED_CHAIN_ID": "97",
            "ERC_MANDATED_MCP_COMMAND": "erc-mandated-mcp",
        },
    )

    payload = read_env_map(env_path)

    assert (
        payload["ERC_MANDATED_VAULT_ADDRESS"]
        == "0x1234567890123456789012345678901234567890"
    )
    assert (
        payload["ERC_MANDATED_FACTORY_ADDRESS"]
        == "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6"
    )
    assert payload["ERC_MANDATED_CHAIN_ID"] == "97"
    assert payload["ERC_MANDATED_MCP_COMMAND"] == "erc-mandated-mcp"
    assert payload["OPENROUTER_API_KEY"] == "leave-me-alone"
