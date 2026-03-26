from __future__ import annotations

from conftest import get_predict_root, parse_skill_frontmatter


def test_skill_manifest_openclaw_contract() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    frontmatter, body = parse_skill_frontmatter(skill_path)

    assert frontmatter["name"] == "predictclaw"
    assert "description" in frontmatter

    openclaw = frontmatter["metadata"]["openclaw"]
    assert openclaw["emoji"]
    assert openclaw["homepage"] == "https://predict.fun"
    assert "uv" in openclaw["requires"]["bins"]
    assert "erc-mandated-mcp" in openclaw["requires"]["bins"]
    for env_name in [
        "PREDICT_ENV",
        "PREDICT_WALLET_MODE",
        "PREDICT_API_KEY",
        "PREDICT_EOA_PRIVATE_KEY",
        "PREDICT_ACCOUNT_ADDRESS",
        "PREDICT_PRIVY_PRIVATE_KEY",
        "ERC_MANDATED_MCP_COMMAND",
        "ERC_MANDATED_VAULT_ADDRESS",
        "ERC_MANDATED_FACTORY_ADDRESS",
        "ERC_MANDATED_VAULT_ASSET_ADDRESS",
        "ERC_MANDATED_VAULT_AUTHORITY",
        "ERC_MANDATED_AUTHORITY_PRIVATE_KEY",
        "ERC_MANDATED_EXECUTOR_PRIVATE_KEY",
        "ERC_MANDATED_BOOTSTRAP_PRIVATE_KEY",
        "OPENROUTER_API_KEY",
    ]:
        assert env_name in openclaw["requires"]["env"]
    assert "primaryEnv" not in openclaw
    assert "install" in openclaw
    install_entries = openclaw["install"]
    assert any(
        entry["kind"] == "brew" and entry["formula"] == "uv"
        for entry in install_entries
    )
    assert any(
        entry["kind"] == "node" and entry["package"] == "@erc-mandated/mcp"
        for entry in install_entries
    )

    assert "{baseDir}" in body
    assert "~/.openclaw/skills/predictclaw/" in body
    assert "only canonical user config root" in body.lower()
    assert "development-only artifact" in body.lower()
    assert "skills.entries.predictclaw.env" in body


def test_skill_manifest_uses_openclaw_single_line_metadata_json() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    text = skill_path.read_text()
    frontmatter_text = text.split("---\n", 2)[1]

    metadata_lines = [
        line for line in frontmatter_text.splitlines() if line.startswith("metadata:")
    ]
    assert len(metadata_lines) == 1
    assert metadata_lines[0].startswith("metadata: {")
    assert '"openclaw"' in metadata_lines[0]


def test_openclaw_install_examples_are_valid() -> None:
    skill_path = get_predict_root() / "SKILL.md"
    _frontmatter, body = parse_skill_frontmatter(skill_path)

    assert "cd {baseDir} && uv sync" in body
    assert "cp template.env .env" in body
    assert "manual install" in body.lower()
    assert "read-only" in body.lower()
    assert "eoa" in body.lower()
    assert "predict-account" in body.lower()
    assert "mandated-vault" in body.lower()
    assert "wallet deposit" in body
    assert "wallet withdraw" in body
    assert "PREDICT_WALLET_MODE" in body
    assert "ERC_MANDATED_VAULT_ADDRESS" in body
    assert "ERC_MANDATED_FACTORY_ADDRESS" in body
    assert "ERC_MANDATED_VAULT_ASSET_ADDRESS" in body
    assert "ERC_MANDATED_VAULT_NAME" in body
    assert "ERC_MANDATED_VAULT_SYMBOL" in body
    assert "ERC_MANDATED_VAULT_AUTHORITY" in body
    assert "ERC_MANDATED_VAULT_SALT" in body
    assert "ERC_MANDATED_MCP_COMMAND" in body
    assert "ERC_MANDATED_CONTRACT_VERSION" in body
    assert "ERC_MANDATED_CHAIN_ID" in body
    assert "manual-only" in body
    assert "vault contract policy authorizes" in body.lower()
    assert "unsupported-in-mandated-vault-v1" in body
    assert "vault-to-predict-account" in body
    assert "funding-required" in body
