from __future__ import annotations

from conftest import get_predict_root, parse_env_file_keys


DOC_COMMANDS = [
    "markets trending",
    "markets search",
    "market 123",
    "wallet status",
    "wallet approve",
    "wallet deposit",
    "wallet bootstrap-vault",
    "wallet redeem-vault",
    "wallet withdraw usdt",
    "wallet withdraw bnb",
    "buy 123 YES 25",
    "positions",
    "position pos-123-yes",
    "hedge scan",
    "hedge analyze 101 202",
]

DOC_ENV_VARS = {
    "PREDICT_STORAGE_DIR",
    "PREDICT_ENV",
    "PREDICT_WALLET_MODE",
    "PREDICT_API_BASE_URL",
    "PREDICT_API_KEY",
    "PREDICT_EOA_PRIVATE_KEY",
    "PREDICT_ACCOUNT_ADDRESS",
    "PREDICT_PRIVY_PRIVATE_KEY",
    "ERC_MANDATED_VAULT_ADDRESS",
    "ERC_MANDATED_FACTORY_ADDRESS",
    "ERC_MANDATED_VAULT_ASSET_ADDRESS",
    "ERC_MANDATED_VAULT_NAME",
    "ERC_MANDATED_VAULT_SYMBOL",
    "ERC_MANDATED_VAULT_AUTHORITY",
    "ERC_MANDATED_VAULT_SALT",
    "ERC_MANDATED_AUTHORITY_PRIVATE_KEY",
    "ERC_MANDATED_EXECUTOR_PRIVATE_KEY",
    "ERC_MANDATED_BOOTSTRAP_PRIVATE_KEY",
    "ERC_MANDATED_ENABLE_BROADCAST",
    "ERC_MANDATED_MCP_COMMAND",
    "ERC_MANDATED_CONTRACT_VERSION",
    "ERC_MANDATED_CHAIN_ID",
    "ERC_MANDATED_ALLOWED_ADAPTERS_ROOT",
    "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX",
    "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW",
    "ERC_MANDATED_FUNDING_WINDOW_SECONDS",
    "OPENROUTER_API_KEY",
    "PREDICT_MODEL",
    "PREDICT_SMOKE_ENV",
    "PREDICT_SMOKE_API_BASE_URL",
    "PREDICT_SMOKE_PRIVATE_KEY",
    "PREDICT_SMOKE_ACCOUNT_ADDRESS",
    "PREDICT_SMOKE_PRIVY_PRIVATE_KEY",
    "PREDICT_SMOKE_API_KEY",
}


def test_documented_commands_exist_in_cli_help() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()

    for command in DOC_COMMANDS:
        assert command in readme
        assert command in skill

    assert "setup mandated-mcp" in readme
    assert "setup mandated-mcp" in skill


def test_documented_env_vars_match_env_example() -> None:
    predict_root = get_predict_root()
    env_keys = parse_env_file_keys(predict_root / "template.env")
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()

    assert env_keys == DOC_ENV_VARS
    for key in DOC_ENV_VARS:
        assert key in readme
        assert key in skill


def test_docs_cover_wallet_modes_and_mandated_vault_boundaries() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill, readme_zh]:
        assert "mandated-vault" in text
        assert "vault-to-predict-account" in text

    for text in [readme, skill]:
        for mode in ["read-only", "eoa", "predict-account", "mandated-vault"]:
            assert mode in text
        assert "PREDICT_WALLET_MODE" in text
        assert "ERC_MANDATED_VAULT_ADDRESS" in text
        assert "ERC_MANDATED_FACTORY_ADDRESS" in text
        assert "ERC_MANDATED_VAULT_ASSET_ADDRESS" in text
        assert "ERC_MANDATED_VAULT_NAME" in text
        assert "ERC_MANDATED_VAULT_SYMBOL" in text
        assert "ERC_MANDATED_VAULT_AUTHORITY" in text
        assert "ERC_MANDATED_VAULT_SALT" in text
        assert "ERC_MANDATED_MCP_COMMAND" in text
        assert "ERC_MANDATED_CONTRACT_VERSION" in text
        assert "ERC_MANDATED_CHAIN_ID" in text
        assert "manual-only" in text
        assert "unsupported-in-mandated-vault-v1" in text
        assert "vault contract policy authorizes" in text.lower()
        assert "funding-required" in text
        assert "Predict Account remains" in text
        assert "vaultAuthority" in text
        assert "vaultExecutor" in text
        assert "bootstrapSigner" in text
        assert "allowedTokenAddresses" in text
        assert "allowedRecipients" in text


def test_docs_explain_redeem_preview_only_flow() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "wallet redeem-vault --preview --json" in text
        assert "redeemableNow" in text
        assert "blockingReason" in text
        assert "ERC4626ExceededMaxRedeem" in text
        assert "preview-only" in text

    assert "wallet redeem-vault --preview --json" in readme_zh
    assert "redeemableNow" in readme_zh
    assert "blockingReason" in readme_zh


def test_docs_explain_flat_metadata_vs_mode_specific_runtime_requirements() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "metadata intentionally lists only the universal entry variables" in text
        assert "OpenClaw's runtime metadata is flat rather than mode-aware" in text
        assert (
            "mode-specific requirements are documented below and enforced by the runtime config validator"
            in text
        )

    assert "metadata 里故意只声明通用入口变量" in readme_zh
    assert "OpenClaw 当前的 runtime metadata 是扁平的，不是按 mode 感知的" in readme_zh
    assert "各模式自己的必填项以下面的示例和运行时配置校验为准" in readme_zh


def test_docs_explain_first_install_bootstrap_layers() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "template.env" in text
        assert "template.readonly.env" in text
        assert "template.eoa.env" in text
        assert "template.predict-account.env" in text
        assert "template.mandated-vault.env" in text
        assert "api.predict.fun" in text
        assert "api-testnet.predict.fun" not in text
        assert "wallet status requires signer configuration" in text
        assert "mainnet market reads require PREDICT_API_KEY" in text
        assert "test-fixture" in text
        assert ".env.example" not in text

    assert "template.env" in readme_zh
    assert "template.readonly.env" in readme_zh
    assert "template.eoa.env" in readme_zh
    assert "template.predict-account.env" in readme_zh
    assert "template.mandated-vault.env" in readme_zh
    assert "api.predict.fun" in readme_zh
    assert "api-testnet.predict.fun" not in readme_zh
    assert "wallet status 需要 signer 配置" in readme_zh
    assert "mainnet 的市场读取需要 PREDICT_API_KEY" in readme_zh
    assert ".env.example" not in readme_zh


def test_docs_explain_predictclaw_version_source_of_truth() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "pyproject.toml" in text
        assert "repository root" in text.lower() or "repo root" in text.lower()

    assert "pyproject.toml" in readme_zh
    assert "仓库根目录" in readme_zh


def test_docs_explain_mandated_mcp_safe_manual_setup_boundary() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()

    for text in [readme, skill]:
        assert "Install the external `erc-mandated-mcp` runtime yourself" in text
        assert "does not globally install packages" in text
        assert "does not auto-edit `.env`" in text
        assert "setup mandated-mcp --install --write-env" not in text

    assert "自行安装外部 `erc-mandated-mcp` runtime" in readme_zh
    assert "不会全局安装包" in readme_zh
    assert "不会自动修改 `.env`" in readme_zh
    assert "setup mandated-mcp --install --write-env" not in readme_zh


def test_docs_shift_mandated_vault_default_to_preview_confirm_bootstrap_flow() -> None:
    predict_root = get_predict_root()
    readme = (predict_root / "README.md").read_text()
    skill = (predict_root / "SKILL.md").read_text()
    readme_zh = (predict_root / "README.zh-CN.md").read_text()
    template = (predict_root / "template.mandated-vault.env").read_text()

    assert "ERC_MANDATED_VAULT_ADDRESS=0xYOUR_DEPLOYED_VAULT" not in template

    for text in [readme, skill]:
        assert "bootstrap-vault" in text
        assert "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6" in text
        assert "preview" in text.lower()
        assert "confirm" in text.lower()
        assert ".env" in text
        assert "manual" in text.lower()

    assert "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6" in readme_zh
    assert "预览" in readme_zh
    assert "确认" in readme_zh
    assert ".env" in readme_zh
    assert "手动" in readme_zh
