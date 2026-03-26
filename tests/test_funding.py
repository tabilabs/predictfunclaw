from __future__ import annotations

import asyncio
from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, cast

import lib
import pytest
from eth_abi.abi import encode as abi_encode
from web3 import Web3

from lib.config import ConfigError, PredictConfig, WalletMode
from lib.config import MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
from lib.mandated_mcp_bridge import (
    FactoryCreateVaultPrepareResult,
    FactoryPredictVaultAddressResult,
    MandatedVaultMcpError,
    MandatedVaultMcpUnavailableError,
    McpTxRequest,
    VaultBootstrapAuthorityConfig,
    VaultBootstrapCreateTx,
    VaultBootstrapResult,
    VaultHealthCheckResult,
)
from lib.session_storage import FundAndActionSessionRecord, SessionStorage
import lib.wallet_manager as wallet_manager_module
from lib.wallet_manager import (
    MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS,
    MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS,
)

FundingService = getattr(lib, "FundingService")


EOA_PRIVATE_KEY = "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01"


@dataclass
class FakeFundingSdk:
    mode: WalletMode = WalletMode.EOA
    signer_address: str = "0xb30741673D351135Cf96564dfD15f8e135f9C310"
    funding_address: str = "0xb30741673D351135Cf96564dfD15f8e135f9C310"
    chain_name: str = "BNB Testnet"
    bnb_balance_wei: int = 2_000_000_000_000_000_000
    usdt_balance_wei: int = 25_000_000_000_000_000_000
    transfer_calls: list[tuple[str, str, int]] | None = None

    def get_bnb_balance_wei(self) -> int:
        return self.bnb_balance_wei

    def get_usdt_balance_wei(self) -> int:
        return self.usdt_balance_wei

    def transfer_usdt(self, destination: str, amount_wei: int) -> dict[str, object]:
        if self.transfer_calls is not None:
            self.transfer_calls.append(("usdt", destination, amount_wei))
        return {"success": True, "txHash": "0xusdt"}

    def transfer_bnb(self, destination: str, amount_wei: int) -> dict[str, object]:
        if self.transfer_calls is not None:
            self.transfer_calls.append(("bnb", destination, amount_wei))
        return {"success": True, "txHash": "0xbnb"}


class AsyncUnsafeFundingSdk(FakeFundingSdk):
    def _assert_outside_event_loop(self) -> None:
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return
        raise AssertionError("balance getter called inside running event loop")

    def get_bnb_balance_wei(self) -> int:
        self._assert_outside_event_loop()
        return super().get_bnb_balance_wei()

    def get_usdt_balance_wei(self) -> int:
        self._assert_outside_event_loop()
        return super().get_usdt_balance_wei()


class CodehashFundingSdk(FakeFundingSdk):
    def __init__(self, *, contract_code: bytes, **kwargs: Any) -> None:
        super().__init__(**kwargs)

        class _Eth:
            def __init__(self, code: bytes) -> None:
                self._code = code

            def get_code(self, _address: str) -> bytes:
                return self._code

        class _Web3:
            def __init__(self, code: bytes) -> None:
                self.eth = _Eth(code)

        class _Builder:
            def __init__(self, code: bytes) -> None:
                self._web3 = _Web3(code)

        self._builder = _Builder(contract_code)


class FakeMandatedBridge:
    def __init__(
        self,
        *,
        predicted_vault: str = "0x1234567890123456789012345678901234567890",
        deployed: bool,
        health_error: Exception | None = None,
        enforce_single_loop_close: bool = False,
    ) -> None:
        self.predicted_vault = predicted_vault
        self.deployed = deployed
        self.health_error = health_error
        self.enforce_single_loop_close = enforce_single_loop_close
        self.connect_loop_id: int | None = None
        self.close_loop_id: int | None = None
        self.close_called = False
        self.bootstrap_calls = 0
        self.bootstrap_modes: list[str] = []
        self.predict_calls = 0
        self.health_check_calls = 0
        self.runtime_ready = True
        self.available_tools = frozenset(
            {
                "vault_bootstrap",
                "factory_predict_vault_address",
                "factory_create_vault_prepare",
                "vault_health_check",
            }
        )
        self.missing_required_tools = frozenset()

    async def connect(self) -> None:
        self.connect_loop_id = id(asyncio.get_running_loop())
        return None

    async def close(self) -> None:
        self.close_called = True
        self.close_loop_id = id(asyncio.get_running_loop())
        if (
            self.enforce_single_loop_close
            and self.connect_loop_id is not None
            and self.connect_loop_id != self.close_loop_id
        ):
            raise RuntimeError("Event loop is closed")
        return None

    async def predict_vault_address(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        authority: str,
        salt: str,
    ) -> FactoryPredictVaultAddressResult:
        self.predict_calls += 1
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert authority.startswith("0x")
        assert salt.startswith("0x")
        return FactoryPredictVaultAddressResult(predictedVault=self.predicted_vault)

    async def vault_bootstrap(
        self,
        *,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        salt: str,
        signer_address: str | None = None,
        mode: str = "plan",
        authority_mode: str | None = None,
        authority: str | None = None,
        executor: str | None = None,
        create_account_context: bool | None = None,
        create_funding_policy: bool | None = None,
        account_context_options: dict[str, Any] | None = None,
        funding_policy_options: dict[str, Any] | None = None,
    ) -> VaultBootstrapResult:
        self.bootstrap_calls += 1
        self.bootstrap_modes.append(mode)
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert salt.startswith("0x")
        assert signer_address is not None and signer_address.startswith("0x")
        assert authority is not None and authority.startswith("0x")
        assert executor is None or executor.startswith("0x")
        assert create_account_context is False
        assert create_funding_policy is False
        assert account_context_options is None
        assert funding_policy_options is None
        if self.health_error is not None:
            message = str(self.health_error).upper()
            undeployed_markers = (
                "VAULT_NOT_DEPLOYED",
                "VAULT_UNDEPLOYED",
                "VAULT_NOT_FOUND",
                "NO_CONTRACT_CODE",
                "NOT DEPLOYED",
            )
            if not any(marker in message for marker in undeployed_markers):
                raise self.health_error
        return VaultBootstrapResult(
            chainId=56,
            mode=cast(Any, mode),
            factory=factory,
            asset=asset,
            signerAddress=signer_address,
            predictedVault=self.predicted_vault,
            deployedVault=self.predicted_vault,
            alreadyDeployed=self.deployed,
            deploymentStatus="confirmed" if self.deployed else "planned",
            authorityConfig=VaultBootstrapAuthorityConfig(
                mode=cast(Any, authority_mode or "single_key"),
                authority=authority,
                executor=executor or signer_address,
            ),
            createTx=(
                None
                if self.deployed
                else VaultBootstrapCreateTx(
                    mode="plan",
                    txRequest=McpTxRequest(
                        **{
                            "from": signer_address,
                            "to": factory,
                            "data": "0xfeedbeef",
                            "value": "0x0",
                            "gas": "0x5208",
                        }
                    ),
                )
            ),
            vaultHealth=(
                VaultHealthCheckResult(
                    blockNumber=101,
                    vault=self.predicted_vault,
                    mandateAuthority="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    authorityEpoch="1",
                    pendingAuthority="0x0000000000000000000000000000000000000000",
                    nonceThreshold="2",
                    totalAssets="0",
                )
                if self.deployed
                else None
            ),
            accountContext=None,
            fundingPolicy=None,
            envBlock="ERC_MANDATED_VAULT_ADDRESS=0x...",
            configBlock='{"vault":"0x..."}',
        )

    async def health_check(self, vault: str) -> VaultHealthCheckResult:
        self.health_check_calls += 1
        assert vault.startswith("0x")
        if self.health_error is not None:
            raise self.health_error
        if not self.deployed:
            raise MandatedVaultMcpError(
                "Mandated-vault MCP tool vault_health_check failed: VAULT_NOT_DEPLOYED vault has no code"
            )
        return VaultHealthCheckResult(
            blockNumber=101,
            vault=vault,
            mandateAuthority="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            authorityEpoch="1",
            pendingAuthority="0x0000000000000000000000000000000000000000",
            nonceThreshold="2",
            totalAssets="0",
        )

    async def prepare_create_vault(
        self,
        *,
        from_address: str,
        factory: str | None,
        asset: str,
        name: str,
        symbol: str,
        authority: str,
        salt: str,
    ) -> FactoryCreateVaultPrepareResult:
        assert from_address.startswith("0x")
        assert factory is not None
        assert asset.startswith("0x")
        assert name
        assert symbol
        assert authority.startswith("0x")
        assert salt.startswith("0x")
        return FactoryCreateVaultPrepareResult(
            predictedVault=self.predicted_vault,
            txRequest=McpTxRequest(
                **{
                    "from": from_address,
                    "to": factory,
                    "data": "0xfeedbeef",
                    "value": "0x0",
                    "gas": "0x5208",
                }
            ),
        )

    async def create_agent_account_context(
        self,
        *,
        agent_id: str,
        vault: str,
        authority: str,
        executor: str,
        asset_registry_ref: str | None = None,
        funding_policy_ref: str | None = None,
        defaults: dict[str, Any] | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Any:
        assert agent_id
        assert vault.startswith("0x")
        assert authority.startswith("0x")
        assert executor.startswith("0x")
        return {
            "accountContext": {
                "agentId": agent_id,
                "chainId": 56,
                "vault": vault,
                "authority": authority,
                "executor": executor,
                "assetRegistryRef": asset_registry_ref,
                "fundingPolicyRef": funding_policy_ref,
                "defaults": defaults,
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": updated_at or "2026-03-09T00:00:00Z",
            }
        }

    async def create_agent_funding_policy(
        self,
        *,
        policy_id: str,
        allowed_token_addresses: list[str] | None = None,
        allowed_recipients: list[str] | None = None,
        max_amount_per_tx: str | None = None,
        max_amount_per_window: str | None = None,
        window_seconds: int | None = None,
        expires_at: str | None = None,
        repeatable: bool | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Any:
        assert policy_id
        assert allowed_recipients
        return {
            "fundingPolicy": {
                "policyId": policy_id,
                "allowedTokenAddresses": allowed_token_addresses,
                "allowedRecipients": allowed_recipients,
                "maxAmountPerTx": max_amount_per_tx,
                "maxAmountPerWindow": max_amount_per_window,
                "windowSeconds": window_seconds,
                "expiresAt": expires_at,
                "repeatable": repeatable,
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": updated_at or "2026-03-09T00:00:00Z",
            }
        }

    async def build_agent_fund_and_action_plan(
        self,
        *,
        account_context: dict[str, Any],
        funding_target: dict[str, Any],
        funding_context: dict[str, Any],
        follow_up_action: dict[str, Any],
        funding_policy: dict[str, Any] | None = None,
    ) -> Any:
        return {
            "accountContext": account_context,
            "fundingPolicy": funding_policy,
            "fundingTarget": {
                **funding_target,
                "fundingShortfallRaw": "1000000000000000000",
            },
            "evaluatedAt": "2026-03-09T00:00:00Z",
            "fundingRequired": True,
            "fundingPlan": {
                "accountContext": account_context,
                "humanReadableSummary": {
                    "kind": "erc20Transfer",
                    "tokenAddress": funding_target["tokenAddress"],
                    "to": funding_target["recipient"],
                    "amountRaw": "1000000000000000000",
                    "symbol": "USDT",
                    "decimals": 18,
                },
            },
            "followUpAction": follow_up_action,
            "followUpActionPlan": {
                "kind": follow_up_action["kind"],
                "executionMode": "custom",
                "summary": "Deferred until buy flow task",
            },
            "steps": [
                {"kind": "fundTargetAccount", "status": "required", "summary": "fund"},
                {"kind": "followUpAction", "status": "pending", "summary": "deferred"},
            ],
            "fundingContext": funding_context,
        }

    async def create_agent_fund_and_action_session(
        self,
        *,
        fund_and_action_plan: dict[str, Any],
        session_id: str | None = None,
        created_at: str | None = None,
    ) -> Any:
        return {
            "session": {
                "sessionId": session_id or "session-funding-overlay",
                "status": "pendingFunding",
                "currentStep": "fundTargetAccount",
                "createdAt": created_at or "2026-03-09T00:00:00Z",
                "updatedAt": "2026-03-09T00:00:00Z",
                "fundAndActionPlan": fund_and_action_plan,
                "fundingStep": {
                    "required": True,
                    "status": "pending",
                    "summary": "Funding required",
                    "updatedAt": "2026-03-09T00:00:00Z",
                    "result": None,
                },
                "followUpStep": {
                    "status": "pending",
                    "summary": "Follow-up pending",
                    "updatedAt": "2026-03-09T00:00:00Z",
                    "reference": None,
                    "result": None,
                },
            }
        }

    async def next_agent_fund_and_action_session_step(
        self,
        *,
        session: dict[str, Any],
    ) -> Any:
        return {
            "session": session,
            "task": {
                "kind": "submitFunding",
                "summary": "Submit vault funding transaction",
                "fundingPlan": session["fundAndActionPlan"].get("fundingPlan"),
            },
        }

    async def create_vault_asset_transfer_result(self, **_: Any) -> Any:
        return SimpleNamespace(
            assetTransferResult=SimpleNamespace(
                model_dump=lambda by_alias=True: {
                    "status": "confirmed",
                    "txHash": "0x" + "ab" * 32,
                }
            )
        )

    async def apply_agent_fund_and_action_session_event(self, **_: Any) -> Any:
        return SimpleNamespace(
            session=SimpleNamespace(
                model_dump=lambda by_alias=True: {
                    "sessionId": "session-funding-overlay",
                    "status": "pendingFollowUp",
                    "currentStep": "followUpAction",
                    "fundAndActionPlan": {
                        "followUpActionPlan": {
                            "kind": "predict.createOrder",
                            "target": "order/123",
                            "executionMode": "offchain-api",
                            "summary": "Submit Predict order",
                        }
                    },
                }
            )
        )

    async def create_agent_follow_up_action_result(self, **_: Any) -> Any:
        return SimpleNamespace(
            followUpActionResult=SimpleNamespace(
                model_dump=lambda by_alias=True: {
                    "status": "succeeded",
                    "reference": {"type": "orderId", "value": "pred-ord-1"},
                    "plan": {
                        "kind": "predict.createOrder",
                        "target": "order/123",
                        "executionMode": "offchain-api",
                        "summary": "Submit Predict order",
                    },
                }
            )
        )


def test_wallet_deposit_reports_eoa_vs_predict_account_address() -> None:
    eoa_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_EOA_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    eoa_service = FundingService(
        eoa_config, sdk_factory=lambda _config: FakeFundingSdk()
    )
    eoa_details = eoa_service.get_deposit_details().to_dict()

    predict_account_config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    predict_account_service = FundingService(
        predict_account_config,
        sdk_factory=lambda _config: FakeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            funding_address="0x1234567890123456789012345678901234567890",
        ),
    )
    predict_account_details = predict_account_service.get_deposit_details().to_dict()

    assert eoa_details["mode"] == "eoa"
    assert eoa_details["fundingAddress"] == eoa_details["signerAddress"]
    assert predict_account_details["mode"] == "predict-account"
    assert (
        predict_account_details["fundingAddress"]
        == "0x1234567890123456789012345678901234567890"
    )
    assert predict_account_details["chain"] == "BNB Testnet"
    assert predict_account_details["acceptedAssets"] == ["BNB", "USDT"]


def test_withdraw_rejects_invalid_destination_or_insufficient_balance() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_EOA_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
        }
    )
    calls: list[tuple[str, str, int]] = []
    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(transfer_calls=calls),
    )

    with pytest.raises(ConfigError, match="checksum address"):
        service.withdraw("usdt", "1", "0xnot-checksummed")

    with pytest.raises(ConfigError, match="greater than zero"):
        service.withdraw("usdt", "0", "0xb30741673D351135Cf96564dfD15f8e135f9C310")

    with pytest.raises(ConfigError, match="Insufficient USDT balance"):
        service.withdraw("usdt", "1000", "0xb30741673D351135Cf96564dfD15f8e135f9C310")

    gas_starved_service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(
            bnb_balance_wei=50_000_000_000_000,
            transfer_calls=calls,
        ),
    )
    with pytest.raises(ConfigError, match="gas headroom"):
        gas_starved_service.withdraw(
            "bnb", "0.1", "0xb30741673D351135Cf96564dfD15f8e135f9C310"
        )

    assert calls == []


def test_wallet_deposit_mandated_vault_reports_explicit_existing_vault() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    service = FundingService(
        config,
        bridge_factory=lambda _config: FakeMandatedBridge(deployed=True),
    )

    payload = service.get_deposit_details().to_dict()

    assert payload["mode"] == "mandated-vault"
    assert payload["activeRoute"] == "vault-control-plane"
    assert payload["routePurpose"] == "bootstrap-or-direct-vault-ops"
    assert payload["fundingAddress"] == "0x2222222222222222222222222222222222222222"
    assert payload["vaultAddressSource"] == "explicit"
    assert payload["vaultExists"] is True
    assert payload["createVaultPreparation"] is None
    assert payload["acceptedAssets"] == ["BNB", "USDT"]


def test_wallet_deposit_mandated_vault_returns_confirmable_preview_when_undeployed() -> (
    None
):
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    service = FundingService(
        config,
        bridge_factory=lambda _config: FakeMandatedBridge(deployed=False),
    )

    payload = service.get_deposit_details().to_dict()
    permission_summary = cast(dict[str, Any], payload["permissionSummary"])
    preview = cast(dict[str, Any], payload["bootstrapPreview"])
    permission_summary = cast(dict[str, Any], payload["permissionSummary"])
    tx_summary = cast(dict[str, Any], preview["txSummary"])

    assert payload["mode"] == "mandated-vault"
    assert payload["fundingAddress"] == "0x1234567890123456789012345678901234567890"
    assert payload["vaultAddressSource"] == "predicted"
    assert payload["vaultExists"] is False
    assert payload["createVaultPreparation"] is None
    assert preview["confirmationRequired"] is True
    assert preview["predictedVault"] == payload["fundingAddress"]
    assert permission_summary["permissionModel"] == "mandated-vault-v1"
    assert permission_summary["vaultAuthority"] == config.mandated_vault_authority
    assert permission_summary["vaultExecutor"] == config.mandated_executor_address
    assert (
        permission_summary["bootstrapSigner"]
        == config.mandated_bootstrap_signer_address
    )
    assert tx_summary["from"] == "0x5555555555555555555555555555555555555555"
    assert tx_summary["to"] == "0x1111111111111111111111111111111111111111"
    assert tx_summary["data"] == "0xfeedbeef"
    assert tx_summary["value"] == "0x0"


def test_wallet_deposit_mandated_vault_prefers_bootstrap_plan_when_available() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "PREDICT_EOA_PRIVATE_KEY": EOA_PRIVATE_KEY,
        }
    )
    bridge = FakeMandatedBridge(deployed=False)
    service = FundingService(config, bridge_factory=lambda _config: bridge)

    payload = service.get_deposit_details().to_dict()
    permission_summary = cast(dict[str, Any], payload["permissionSummary"])
    preview = cast(dict[str, Any], payload["bootstrapPreview"])

    assert payload["vaultExists"] is False
    assert preview["factory"] == "0x6eFC613Ece5D95e4a7b69B4EddD332CeeCbb61c6"
    assert preview["confirmationRequired"] is True
    assert preview["signerAddress"] == config.mandated_vault_authority
    assert permission_summary["permissionModel"] == "mandated-vault-v1"
    assert bridge.bootstrap_calls == 1
    assert bridge.bootstrap_modes == ["plan"]
    assert bridge.predict_calls == 0
    assert bridge.health_check_calls == 0


def test_wallet_deposit_mandated_vault_fails_closed_on_mcp_outage() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    service = FundingService(
        config,
        bridge_factory=lambda _config: FakeMandatedBridge(
            deployed=False,
            health_error=MandatedVaultMcpUnavailableError(
                "Mandated-vault MCP process exited before completing the request"
            ),
        ),
    )

    with pytest.raises(MandatedVaultMcpUnavailableError):
        service.get_deposit_details()


def test_wallet_deposit_mandated_vault_uses_single_loop_bridge_lifecycle() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    bridge = FakeMandatedBridge(
        deployed=True,
        enforce_single_loop_close=True,
    )
    service = FundingService(
        config,
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()

    assert payload["vaultExists"] is True
    assert bridge.close_called is True
    assert bridge.connect_loop_id is not None
    assert bridge.close_loop_id is not None
    assert bridge.connect_loop_id == bridge.close_loop_id


def test_wallet_withdraw_mandated_vault_fails_closed_with_v1_guidance() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
        }
    )
    service = FundingService(config)

    with pytest.raises(ConfigError) as error:
        service.withdraw("usdt", "1", "0xb30741673D351135Cf96564dfD15f8e135f9C310")

    message = str(error.value)
    assert "unsupported-in-mandated-vault-v1" in message
    assert "protected funding/control-plane operations" in message
    assert "predict.fun trading parity" in message


def test_wallet_deposit_predict_account_with_vault_overlay_exposes_route_and_plan() -> (
    None
):
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ERC_MANDATED_CHAIN_ID": "56",
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX": "5000000000000000000",
            "ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW": "10000000000000000000",
            "ERC_MANDATED_FUNDING_WINDOW_SECONDS": "3600",
        }
    )
    bridge = FakeMandatedBridge(deployed=True)
    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            signer_address="0x7777777777777777777777777777777777777777",
            funding_address="0x1234567890123456789012345678901234567890",
            usdt_balance_wei=2_000_000_000_000_000_000,
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()
    orchestration = cast(dict[str, Any], payload["fundingOrchestration"])
    permission_summary = cast(dict[str, Any], payload["permissionSummary"])
    account_context = cast(dict[str, Any], orchestration["accountContext"])
    funding_policy = cast(dict[str, Any], orchestration["fundingPolicy"])
    funding_target = cast(dict[str, Any], orchestration["fundingTarget"])
    funding_plan = cast(dict[str, Any], orchestration["fundingPlan"])
    funding_session = cast(dict[str, Any], orchestration["fundingSession"])
    funding_next_step = cast(dict[str, Any], orchestration["fundingNextStep"])
    funding_task = cast(dict[str, Any], funding_next_step["task"])

    assert payload["mode"] == "predict-account"
    assert payload["activeRoute"] == "vault-to-predict-account"
    assert payload["routePurpose"] == "predict-account-top-up-and-trading"
    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert (
        payload["predictAccountAddress"] == "0x1234567890123456789012345678901234567890"
    )
    assert payload["tradeSignerAddress"] == "0x7777777777777777777777777777777777777777"
    assert payload["vaultAddress"] == "0x2222222222222222222222222222222222222222"
    assert payload["vaultAddressSource"] == "explicit"
    assert payload["vaultExists"] is True
    assert permission_summary["permissionModel"] == "vault-to-predict-account-overlay"
    assert permission_summary["allowedTokenAddresses"] == [
        config.mandated_vault_asset_address
    ]
    assert permission_summary["allowedRecipients"] == [payload["predictAccountAddress"]]
    assert account_context["executor"] == "0x5555555555555555555555555555555555555555"
    assert (
        account_context["defaults"]["allowedAdaptersRoot"]
        == MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
    )
    assert (
        account_context["defaults"]["maxDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS
    )
    assert (
        account_context["defaults"]["maxCumulativeDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS
    )
    assert (
        funding_plan["fundingContext"]["allowedAdaptersRoot"]
        == MANDATED_ALLOWED_ADAPTERS_ROOT_DEFAULT
    )
    assert (
        funding_plan["fundingContext"]["maxDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_DRAWDOWN_BPS
    )
    assert (
        funding_plan["fundingContext"]["maxCumulativeDrawdownBps"]
        == MANDATED_FUNDING_TRANSFER_MAX_CUMULATIVE_DRAWDOWN_BPS
    )
    assert funding_policy["maxAmountPerTx"] == "5000000000000000000"
    assert funding_policy["maxAmountPerWindow"] == "10000000000000000000"
    assert funding_policy["windowSeconds"] == 3600
    assert funding_target["recipient"] == "0x1234567890123456789012345678901234567890"
    assert (
        funding_target["tokenAddress"] == "0x4444444444444444444444444444444444444444"
    )
    assert funding_session["sessionId"] == "session-funding-overlay"
    assert funding_session["currentStep"] == "fundTargetAccount"
    assert funding_task["kind"] == "submitFunding"


def test_funding_service_uses_stored_overlay_session_binding(tmp_path) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": EOA_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    SessionStorage(config.storage_dir).upsert(
        FundAndActionSessionRecord(
            session_id="session-funding-overlay",
            predict_account_address="0x1234567890123456789012345678901234567890",
            market_id="123",
            position_id="pos-123-yes",
            outcome="YES",
            order_hash=None,
            session_scope="specific-trade",
            funding_plan={"evaluatedAt": "2026-03-24T00:00:00Z"},
            funding_session={
                "sessionId": "session-funding-overlay",
                "status": "pendingFunding",
            },
            funding_next_step={"task": {"kind": "submitFunding"}},
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )
    )

    bridge = FakeMandatedBridge(deployed=True)
    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            signer_address="0x7777777777777777777777777777777777777777",
            funding_address="0x1234567890123456789012345678901234567890",
            usdt_balance_wei=2_000_000_000_000_000_000,
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()
    binding = cast(dict[str, Any], payload["sessionBinding"])

    assert payload["sessionScope"] == "specific-trade"
    assert binding["sessionId"] == "session-funding-overlay"


def test_wallet_deposit_overlay_can_resolve_asset_and_authority_from_vault_address(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_CHAIN_ID": "56",
        }
    )
    bridge = FakeMandatedBridge(deployed=True)

    monkeypatch.setattr(
        wallet_manager_module,
        "resolve_overlay_vault_runtime_metadata",
        lambda *args, **kwargs: {
            "vaultAuthority": "0x5555555555555555555555555555555555555555",
            "vaultAssetAddress": "0x4444444444444444444444444444444444444444",
        },
        raising=False,
    )

    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            signer_address="0x7777777777777777777777777777777777777777",
            funding_address="0x1234567890123456789012345678901234567890",
            usdt_balance_wei=2_000_000_000_000_000_000,
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()

    assert payload["activeRoute"] == "vault-to-predict-account"
    assert payload["vaultAddress"] == "0x2222222222222222222222222222222222222222"
    permission_summary = cast(dict[str, Any], payload["permissionSummary"])
    assert (
        permission_summary["vaultAuthority"]
        == "0x5555555555555555555555555555555555555555"
    )
    assert permission_summary["allowedTokenAddresses"] == [
        "0x4444444444444444444444444444444444444444"
    ]


def test_funding_service_continue_funding_updates_session_and_next_step(
    tmp_path,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": EOA_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    SessionStorage(config.storage_dir).upsert(
        FundAndActionSessionRecord(
            session_id="session-funding-overlay",
            predict_account_address="0x1234567890123456789012345678901234567890",
            market_id="123",
            position_id="pos-123-yes",
            outcome="YES",
            order_hash=None,
            session_scope="specific-trade",
            funding_plan={
                "humanReadableSummary": {
                    "tokenAddress": "0x4444444444444444444444444444444444444444",
                    "to": "0x1234567890123456789012345678901234567890",
                    "amountRaw": "1000000000000000000",
                }
            },
            funding_session={
                "sessionId": "session-funding-overlay",
                "status": "pendingFunding",
                "currentStep": "fundTargetAccount",
                "fundAndActionPlan": {
                    "followUpActionPlan": {
                        "kind": "predict.createOrder",
                        "target": "order/123",
                        "executionMode": "offchain-api",
                        "summary": "Submit Predict order",
                    }
                },
            },
            funding_next_step={
                "task": {
                    "kind": "submitFunding",
                    "fundingPlan": {
                        "humanReadableSummary": {
                            "tokenAddress": "0x4444444444444444444444444444444444444444",
                            "to": "0x1234567890123456789012345678901234567890",
                            "amountRaw": "1000000000000000000",
                        }
                    },
                }
            },
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )
    )

    class ContinuationBridge:
        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def create_vault_asset_transfer_result(self, **_: Any) -> Any:
            return SimpleNamespace(
                assetTransferResult=SimpleNamespace(
                    model_dump=lambda by_alias=True: {
                        "status": "confirmed",
                        "txHash": "0x" + "ab" * 32,
                    }
                )
            )

        async def apply_agent_fund_and_action_session_event(self, **_: Any) -> Any:
            return SimpleNamespace(
                session=SimpleNamespace(
                    model_dump=lambda by_alias=True: {
                        "sessionId": "session-funding-overlay",
                        "status": "pendingFollowUp",
                        "currentStep": "followUpAction",
                        "fundAndActionPlan": {
                            "followUpActionPlan": {
                                "kind": "predict.createOrder",
                                "target": "order/123",
                                "executionMode": "offchain-api",
                                "summary": "Submit Predict order",
                            }
                        },
                    }
                )
            )

        async def next_agent_fund_and_action_session_step(self, **_: Any) -> Any:
            return SimpleNamespace(
                model_dump=lambda by_alias=True: {
                    "session": {
                        "sessionId": "session-funding-overlay",
                        "status": "pendingFollowUp",
                        "currentStep": "followUpAction",
                    },
                    "task": {
                        "kind": "submitFollowUp",
                        "followUpActionPlan": {
                            "kind": "predict.createOrder",
                            "target": "order/123",
                            "executionMode": "offchain-api",
                            "summary": "Submit Predict order",
                        },
                    },
                }
            )

    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(mode=WalletMode.PREDICT_ACCOUNT),
        bridge_factory=lambda _config: ContinuationBridge(),
    )

    result = service.continue_funding(tx_hash="0x" + "ab" * 32)

    assert result["session"]["status"] == "pendingFollowUp"
    assert result["nextStep"]["task"]["kind"] == "submitFollowUp"
    stored = SessionStorage(config.storage_dir).get_active_session(
        predict_account_address="0x1234567890123456789012345678901234567890"
    )
    assert stored is not None
    assert stored.funding_session["status"] == "pendingFollowUp"


def test_funding_service_continue_follow_up_updates_session_to_succeeded(
    tmp_path,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": str(tmp_path),
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": EOA_PRIVATE_KEY,
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    SessionStorage(config.storage_dir).upsert(
        FundAndActionSessionRecord(
            session_id="session-funding-overlay",
            predict_account_address="0x1234567890123456789012345678901234567890",
            market_id="123",
            position_id="pos-123-yes",
            outcome="YES",
            order_hash=None,
            session_scope="specific-trade",
            funding_plan={"evaluatedAt": "2026-03-24T00:00:00Z"},
            funding_session={
                "sessionId": "session-funding-overlay",
                "status": "pendingFollowUp",
                "currentStep": "followUpAction",
                "fundAndActionPlan": {
                    "followUpActionPlan": {
                        "kind": "predict.createOrder",
                        "target": "order/123",
                        "executionMode": "offchain-api",
                        "summary": "Submit Predict order",
                    }
                },
            },
            funding_next_step={
                "task": {
                    "kind": "submitFollowUp",
                    "followUpActionPlan": {
                        "kind": "predict.createOrder",
                        "target": "order/123",
                        "executionMode": "offchain-api",
                        "summary": "Submit Predict order",
                    },
                }
            },
            created_at="2026-03-24T00:00:00Z",
            updated_at="2026-03-24T00:00:00Z",
        )
    )

    class FollowUpBridge:
        async def connect(self) -> None:
            return None

        async def close(self) -> None:
            return None

        async def create_agent_follow_up_action_result(self, **_: Any) -> Any:
            return SimpleNamespace(
                followUpActionResult=SimpleNamespace(
                    model_dump=lambda by_alias=True: {
                        "status": "succeeded",
                        "reference": {"type": "orderId", "value": "pred-ord-1"},
                        "plan": {
                            "kind": "predict.createOrder",
                            "target": "order/123",
                            "executionMode": "offchain-api",
                            "summary": "Submit Predict order",
                        },
                    }
                )
            )

        async def apply_agent_fund_and_action_session_event(self, **_: Any) -> Any:
            return SimpleNamespace(
                session=SimpleNamespace(
                    model_dump=lambda by_alias=True: {
                        "sessionId": "session-funding-overlay",
                        "status": "succeeded",
                        "currentStep": "followUpAction",
                    }
                )
            )

    service = FundingService(
        config,
        sdk_factory=lambda _config: FakeFundingSdk(mode=WalletMode.PREDICT_ACCOUNT),
        bridge_factory=lambda _config: FollowUpBridge(),
    )

    result = service.continue_follow_up(
        reference_type="orderId",
        reference_value="pred-ord-1",
        output={"orderId": "pred-ord-1"},
    )

    assert result["session"]["status"] == "succeeded"
    stored = SessionStorage(config.storage_dir).get_active_session(
        predict_account_address="0x1234567890123456789012345678901234567890"
    )
    assert stored is None


def test_wallet_deposit_predict_account_overlay_reads_balances_outside_event_loop() -> (
    None
):
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        }
    )
    bridge = FakeMandatedBridge(deployed=True)
    service = FundingService(
        config,
        sdk_factory=lambda _config: AsyncUnsafeFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            signer_address="0x7777777777777777777777777777777777777777",
            funding_address="0x1234567890123456789012345678901234567890",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()

    assert payload["fundingRoute"] == "vault-to-predict-account"
    assert payload["bnbBalanceWei"] == 2_000_000_000_000_000_000
    assert payload["usdtBalanceWei"] == 25_000_000_000_000_000_000


def test_wallet_deposit_predict_account_overlay_computes_dynamic_adapter_root() -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "testnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "predict-account",
            "PREDICT_ACCOUNT_ADDRESS": "0x1234567890123456789012345678901234567890",
            "PREDICT_PRIVY_PRIVATE_KEY": "0x59c6995e998f97a5a0044976f4d060f5d89c8b8c7f11b9aa0dbf3f0f7c7c1e01",
            "ERC_MANDATED_VAULT_ADDRESS": "0x2222222222222222222222222222222222222222",
            "ERC_MANDATED_FACTORY_ADDRESS": "0x1111111111111111111111111111111111111111",
            "ERC_MANDATED_VAULT_ASSET_ADDRESS": "0x4444444444444444444444444444444444444444",
            "ERC_MANDATED_VAULT_NAME": "Mandated Vault",
            "ERC_MANDATED_VAULT_SYMBOL": "MVLT",
            "ERC_MANDATED_VAULT_AUTHORITY": "0x5555555555555555555555555555555555555555",
            "ERC_MANDATED_VAULT_SALT": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
            "ERC_MANDATED_CHAIN_ID": "56",
        }
    )
    bridge = FakeMandatedBridge(deployed=True)
    service = FundingService(
        config,
        sdk_factory=lambda _config: CodehashFundingSdk(
            mode=WalletMode.PREDICT_ACCOUNT,
            signer_address="0x7777777777777777777777777777777777777777",
            funding_address="0x1234567890123456789012345678901234567890",
            contract_code=b"\x60\x60\x60\x40\x52",
        ),
        bridge_factory=lambda _config: bridge,
    )

    payload = service.get_deposit_details().to_dict()
    orchestration = cast(dict[str, Any], payload["fundingOrchestration"])
    account_context = cast(dict[str, Any], orchestration["accountContext"])
    funding_plan = cast(dict[str, Any], orchestration["fundingPlan"])
    codehash = Web3.keccak(b"\x60\x60\x60\x40\x52")
    expected_root = (
        "0x"
        + Web3.keccak(
            abi_encode(
                ["address", "bytes32"],
                [
                    Web3.to_checksum_address(
                        "0x4444444444444444444444444444444444444444"
                    ),
                    codehash,
                ],
            )
        ).hex()
    )

    assert account_context["defaults"]["allowedAdaptersRoot"] == expected_root
    assert funding_plan["fundingContext"]["allowedAdaptersRoot"] == expected_root


def test_preview_vault_redeem_reports_structured_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "mainnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "PREDICT_API_KEY": "test-api-key",
            "PREDICT_EOA_PRIVATE_KEY": EOA_PRIVATE_KEY,
            "ERC_MANDATED_BOOTSTRAP_PRIVATE_KEY": "0x8f2a559490d0123eb5eb0f5d8d8c441f6df5e0a8fba4b4c8fdd0f760b6f6f4a2",
        }
    )

    class _Call:
        def __init__(self, value: Any = None, error: Exception | None = None) -> None:
            self._value = value
            self._error = error

        def call(self, *_args: Any, **_kwargs: Any) -> Any:
            if self._error is not None:
                raise self._error
            return self._value

    class _Functions:
        def name(self) -> _Call:
            return _Call("Predict Mainnet USDT Vault")

        def symbol(self) -> _Call:
            return _Call("pmUSDT")

        def decimals(self) -> _Call:
            return _Call(18)

        def balanceOf(self, _holder: str) -> _Call:
            return _Call(28_990_000_000_000_000_000)

        def asset(self) -> _Call:
            return _Call("0x55d398326f99059fF775485246999027B3197955")

        def totalAssets(self) -> _Call:
            return _Call(23_990_000_000_000_000_000)

        def maxRedeem(self, _holder: str) -> _Call:
            return _Call(28_990_000_000_000_000_000)

        def maxWithdraw(self, _holder: str) -> _Call:
            return _Call(None)

        def previewRedeem(self, _shares: int) -> _Call:
            return _Call(23_990_000_000_000_000_000)

        def redeem(self, _shares: int, _receiver: str, _owner: str) -> _Call:
            return _Call(
                error=Exception(
                    "0xb94abeec0000000000000000000000007df0ba782d85b93266b595d496088abfac82395000000000000000000000000000000000000000000000000192512b678693000000000000000000000000000000000000000000000000000000000000000000"
                )
            )

    class _Eth:
        def contract(self, *_args: Any, **_kwargs: Any) -> Any:
            return SimpleNamespace(functions=_Functions())

    class _FakeWeb3:
        HTTPProvider = staticmethod(lambda *_args, **_kwargs: object())

        def __init__(self, _provider: object) -> None:
            self.eth = _Eth()

        @staticmethod
        def to_checksum_address(address: str) -> str:
            return Web3.to_checksum_address(address)

    monkeypatch.setattr(lib.funding_service, "Web3", _FakeWeb3)

    preview = FundingService(config).preview_vault_redeem(
        share_token="0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7",
        holder="0x7df0ba782D85B93266b595d496088ABFAc823950",
        redeem_all=True,
    )
    payload = preview.to_dict()

    assert payload["shareToken"] == Web3.to_checksum_address(
        "0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7"
    )
    assert payload["holder"] == "0x7df0ba782D85B93266b595d496088ABFAc823950"
    assert payload["shareTokenMetadata"]["symbol"] == "pmUSDT"
    assert (
        payload["underlyingAsset"]["address"]
        == "0x55d398326f99059fF775485246999027B3197955"
    )
    assert payload["redeemableNow"] is False
    assert payload["blockingReason"] == "erc4626-max-redeem-blocked"
    assert payload["contractError"]["code"] == "ERC4626ExceededMaxRedeem"
    assert payload["holderRoleMatches"]["bootstrapSigner"] is False


def test_preview_vault_redeem_can_report_redeemable_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config = PredictConfig.from_env(
        {
            "PREDICT_ENV": "mainnet",
            "PREDICT_STORAGE_DIR": "/tmp/predict",
            "PREDICT_WALLET_MODE": "mandated-vault",
            "PREDICT_API_KEY": "test-api-key",
            "PREDICT_EOA_PRIVATE_KEY": EOA_PRIVATE_KEY,
        }
    )

    class _Call:
        def __init__(self, value: Any = None) -> None:
            self._value = value

        def call(self, *_args: Any, **_kwargs: Any) -> Any:
            return self._value

    class _Functions:
        def name(self) -> _Call:
            return _Call("Predict Mainnet USDT Vault")

        def symbol(self) -> _Call:
            return _Call("pmUSDT")

        def decimals(self) -> _Call:
            return _Call(18)

        def balanceOf(self, _holder: str) -> _Call:
            return _Call(1_000_000_000_000_000_000)

        def asset(self) -> _Call:
            return _Call("0x55d398326f99059fF775485246999027B3197955")

        def totalAssets(self) -> _Call:
            return _Call(1_000_000_000_000_000_000)

        def maxRedeem(self, _holder: str) -> _Call:
            return _Call(1_000_000_000_000_000_000)

        def maxWithdraw(self, _holder: str) -> _Call:
            return _Call(1_000_000_000_000_000_000)

        def previewRedeem(self, _shares: int) -> _Call:
            return _Call(900_000_000_000_000_000)

        def redeem(self, _shares: int, _receiver: str, _owner: str) -> _Call:
            return _Call(900_000_000_000_000_000)

    class _Eth:
        def contract(self, *_args: Any, **_kwargs: Any) -> Any:
            return SimpleNamespace(functions=_Functions())

    class _FakeWeb3:
        HTTPProvider = staticmethod(lambda *_args, **_kwargs: object())

        def __init__(self, _provider: object) -> None:
            self.eth = _Eth()

        @staticmethod
        def to_checksum_address(address: str) -> str:
            return Web3.to_checksum_address(address)

    monkeypatch.setattr(lib.funding_service, "Web3", _FakeWeb3)

    preview = FundingService(config).preview_vault_redeem(
        share_token="0x4a88c1c95d0f59ee87c3286ed23e9dcdf4cf08d7",
        holder=config.mandated_bootstrap_signer_address,
        redeem_all=True,
    )
    payload = preview.to_dict()

    assert payload["redeemableNow"] is True
    assert payload.get("blockingReason") is None
    assert payload.get("contractError") is None
