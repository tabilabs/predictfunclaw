from __future__ import annotations

import json
import subprocess
import sys
import os
from pathlib import Path

from conftest import get_predict_root


def run_predictclaw(*args: str) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_wallet(*args: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "wallet.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def run_predictclaw_with_env(
    *args: str, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    predict_root = get_predict_root()
    command_env = os.environ.copy()
    command_env["PREDICTCLAW_DISABLE_LOCAL_ENV"] = "1"
    command_env.update(env)
    return subprocess.run(
        [sys.executable, str(predict_root / "scripts" / "predictclaw.py"), *args],
        cwd=predict_root,
        env=command_env,
        capture_output=True,
        text=True,
        check=False,
    )


def write_trade_api_error_sitecustomize(tmp_path: Path) -> Path:
    patch_root = tmp_path / "trade-api-error-patch"
    patch_root.mkdir(parents=True, exist_ok=True)
    (patch_root / "sitecustomize.py").write_text(
        """
from __future__ import annotations

from lib.api import PredictApiError
import lib.trade_service as trade_service


async def _fail_buy(self, *args, **kwargs):
    raise PredictApiError(
        'predict.fun API request failed for POST /v1/orders with status 403: {"success":false,"code":403,"error":"forbidden","message":"This operation is not available in your jurisdiction"}',
        status_code=403,
        method='POST',
        path='/v1/orders',
    )


trade_service.TradeService.buy = _fail_buy
""".strip(),
        encoding="utf-8",
    )
    return patch_root


def write_redeem_preview_sitecustomize(tmp_path: Path) -> Path:
    patch_root = tmp_path / "redeem-preview-patch"
    patch_root.mkdir(parents=True, exist_ok=True)
    (patch_root / "sitecustomize.py").write_text(
        """
from __future__ import annotations

from types import SimpleNamespace
import lib.funding_service as funding_service


def _preview_vault_redeem(self, *, share_token, holder=None, redeem_all=False):
    return SimpleNamespace(
        to_dict=lambda: {
            'chainId': 56,
            'chain': 'BNB Mainnet',
            'shareToken': share_token,
            'holder': holder or '0x7df0ba782D85B93266b595d496088ABFAc823950',
            'shareBalanceWei': 28990000000000000000,
            'requestedSharesWei': 28990000000000000000 if redeem_all else 0,
            'redeemableNow': False,
            'blockingReason': 'erc4626-max-redeem-blocked',
            'recommendedNextAction': 'Inspect vault-specific withdrawal rules before any real redeem transaction.',
            'shareTokenMetadata': {'name': 'Predict Mainnet USDT Vault', 'symbol': 'pmUSDT', 'decimals': 18},
            'underlyingAsset': {'address': '0x55d398326f99059fF775485246999027B3197955', 'symbol': 'USDT', 'decimals': 18},
            'configuredRoles': {
                'vaultAuthority': '0xD2154B7B1f3DB28a1A654F1BF2f778e8C896139b',
                'vaultExecutor': '0x7df0ba782D85B93266b595d496088ABFAc823950',
                'bootstrapSigner': '0x7df0ba782D85B93266b595d496088ABFAc823950',
            },
            'holderRoleMatches': {
                'vaultAuthority': False,
                'vaultExecutor': True,
                'bootstrapSigner': True,
            },
            'contractError': {'code': 'ERC4626ExceededMaxRedeem'},
        }
    )


funding_service.FundingService.preview_vault_redeem = _preview_vault_redeem
""".strip(),
        encoding="utf-8",
    )
    return patch_root


def test_top_level_help_exposes_planned_command_surface() -> None:
    result = run_predictclaw("--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    for command in [
        "markets",
        "market",
        "wallet",
        "buy",
        "positions",
        "position",
        "hedge",
        "setup",
    ]:
        assert command in combined
    assert "PREDICT_EOA_PRIVATE_KEY" in combined
    assert "PREDICT_WALLET_MODE" in combined
    assert "Predict Account" in combined
    assert "testnet" in combined.lower()
    assert "mainnet" in combined.lower()
    for mode in ["read-only", "eoa", "predict-account", "mandated-vault"]:
        assert mode in combined
    for env_name in [
        "ERC_MANDATED_VAULT_ADDRESS",
        "ERC_MANDATED_FACTORY_ADDRESS",
        "ERC_MANDATED_VAULT_ASSET_ADDRESS",
        "ERC_MANDATED_VAULT_NAME",
        "ERC_MANDATED_VAULT_SYMBOL",
        "ERC_MANDATED_VAULT_AUTHORITY",
        "ERC_MANDATED_VAULT_SALT",
        "ERC_MANDATED_MCP_COMMAND",
        "ERC_MANDATED_CONTRACT_VERSION",
        "ERC_MANDATED_CHAIN_ID",
        "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX",
        "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW",
        "ERC_MANDATED_FUNDING_WINDOW_SECONDS",
    ]:
        assert env_name in combined
    assert "manual-only" in combined
    assert "vault contract policy authorizes" in combined.lower()
    assert "unsupported-in-mandated-vault-v1" in combined
    assert "vault-to-predict-account" in combined
    assert "funding-required" in combined


def test_setup_help_exposes_mandated_mcp_installer() -> None:
    result = run_predictclaw("setup", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "mandated-mcp" in combined
    assert "--install" in combined
    assert "--write-env" in combined
    assert "erc-mandated-mcp" in combined


def test_unknown_command_fails_cleanly() -> None:
    result = run_predictclaw("nonsense")

    assert result.returncode != 0
    combined = result.stdout + result.stderr
    assert "Unknown command" in combined
    assert "Traceback" not in combined


def test_wallet_deposit_help_documents_funding_semantics() -> None:
    result = run_predictclaw("wallet", "deposit", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "funding guidance" in combined.lower()
    assert "predict account" in combined.lower()
    assert "bnb" in combined.lower()
    assert "usdt" in combined.lower()


def test_wallet_help_exposes_public_continuation_commands() -> None:
    result = run_predictclaw("wallet", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "continue-funding" in combined
    assert "continue-follow-up" in combined


def test_wallet_bootstrap_help_documents_preview_and_confirmation_flags() -> None:
    result = run_predictclaw("wallet", "bootstrap-vault", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--confirm" in combined
    assert "--json" in combined
    assert "preview" in combined.lower()
    assert "confirmation" in combined.lower()
    assert "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6" in combined


def test_wallet_redeem_vault_help_documents_preview_only_flow() -> None:
    result = run_predictclaw("wallet", "redeem-vault", "--help")

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert "--share-token" in combined
    assert "--holder" in combined
    assert "--all" in combined
    assert "preview" in combined.lower()
    assert "underlying asset" in combined.lower()


def test_wallet_redeem_vault_preview_outputs_structured_json(tmp_path: Path) -> None:
    patch_root = write_redeem_preview_sitecustomize(tmp_path)
    env = {
        "PREDICT_ENV": "mainnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "PREDICT_API_KEY": "test-api-key",
        "PREDICT_EOA_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        "PYTHONPATH": f"{patch_root}{os.pathsep}" + os.environ.get("PYTHONPATH", ""),
    }

    result = run_wallet(
        "redeem-vault",
        "--share-token",
        "0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7",
        "--holder",
        "0x7df0ba782D85B93266b595d496088ABFAc823950",
        "--all",
        "--json",
        env=env,
    )

    assert result.returncode == 0
    combined = result.stdout + result.stderr
    assert '"blockingReason": "erc4626-max-redeem-blocked"' in combined
    assert '"shareToken": "0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7"' in combined


def test_wallet_redeem_vault_confirm_fails_closed_until_supported() -> None:
    env = {
        "PREDICT_ENV": "mainnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "PREDICT_EOA_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }

    result = run_wallet(
        "redeem-vault",
        "--share-token",
        "0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7",
        "--confirm",
        env=env,
    )

    assert result.returncode == 1
    combined = result.stdout + result.stderr
    assert "preview-only" in combined.lower()


def test_wallet_status_and_deposit_fail_cleanly_when_mcp_is_unavailable() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        "ERC_MANDATED_MCP_COMMAND": "missing-mcp-binary-for-test",
    }

    status = run_wallet("status", "--json", env=env)
    deposit = run_wallet("deposit", "--json", env=env)

    assert status.returncode == 1
    assert deposit.returncode == 1
    status_combined = status.stdout + status.stderr
    deposit_combined = deposit.stdout + deposit.stderr
    assert "Traceback" not in status_combined
    assert "Traceback" not in deposit_combined
    assert "mandated-vault mcp" in status_combined.lower()
    assert "mandated-vault mcp" in deposit_combined.lower()


def test_wallet_status_json_surfaces_route_conflict_guidance() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
        "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }

    status = run_wallet("status", "--json", env=env)

    assert status.returncode == 1
    assert status.stderr == ""
    payload = json.loads(status.stdout)
    assert payload["success"] is False
    assert payload["errorCode"] == "route-mode-conflict"
    assert payload["activeMode"] == "mandated-vault"
    assert payload["activeRoute"] == "vault-control-plane"
    assert payload["recommendedMode"] == "predict-account"
    assert payload["recommendedRoute"] == "vault-to-predict-account"
    assert payload["detectedCapabilities"]["predictAccountCredentials"] is True
    assert payload["detectedCapabilities"]["mandatedVaultConfig"] is True


def test_wallet_deposit_text_surfaces_route_conflict_guidance_without_traceback() -> (
    None
):
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
        "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
    }

    deposit = run_wallet("deposit", env=env)

    assert deposit.returncode == 1
    combined = deposit.stdout + deposit.stderr
    assert "vault-control-plane" in combined
    assert "vault-to-predict-account" in combined
    assert "PREDICT_WALLET_MODE=predict-account" in combined
    assert "Traceback" not in combined


def test_mandated_vault_unsupported_flows_fail_closed_without_traceback() -> None:
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": "/tmp/predict",
        "PREDICT_WALLET_MODE": "mandated-vault",
        "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
    }

    wallet_approve = run_wallet("approve", "--json", env=env)
    wallet_withdraw = run_wallet(
        "withdraw",
        "usdt",
        "1",
        "0xb30741673D351135Cf96564dfD15f8e135f9C310",
        "--json",
        env=env,
    )
    buy = run_predictclaw_with_env("buy", "123", "YES", "25", env=env)
    positions = run_predictclaw_with_env("positions", "--json", env=env)
    position = run_predictclaw_with_env("position", "pos-123-yes", "--json", env=env)
    hedge_scan = run_predictclaw_with_env("hedge", "scan", "--json", env=env)

    for result in [
        wallet_approve,
        wallet_withdraw,
        buy,
        positions,
        position,
        hedge_scan,
    ]:
        assert result.returncode == 1
        combined = result.stdout + result.stderr
        assert "unsupported-in-mandated-vault-v1" in combined
        assert "Traceback" not in combined


def test_buy_api_error_fails_closed_without_traceback_in_json_mode(
    tmp_path: Path,
) -> None:
    patch_root = write_trade_api_error_sitecustomize(tmp_path)
    env = {
        "PREDICT_ENV": "testnet",
        "PREDICT_STORAGE_DIR": str(tmp_path),
        "PYTHONPATH": str(patch_root),
    }

    result = run_predictclaw_with_env("buy", "123", "YES", "25", "--json", env=env)

    assert result.returncode == 1
    assert result.stderr == ""
    assert "Traceback" not in result.stdout
    payload = result.stdout.strip()
    assert '"success": false' in payload
    assert '"error": "PredictApiError"' in payload
    assert '"statusCode": 403' in payload
    assert '"path": "/v1/orders"' in payload
    assert "jurisdiction" in payload.lower()
