---
name: predictclaw
description: Predict.fun skill with a PolyClaw-style CLI for markets, wallet funding, trading, positions, and hedging.
metadata: {"openclaw":{"emoji":"🔮","homepage":"https://predict.fun","primaryEnv":"PREDICT_PRIVATE_KEY","requires":{"bins":["uv"],"env":["PREDICT_ENV","PREDICT_WALLET_MODE","PREDICT_PRIVATE_KEY","PREDICT_ACCOUNT_ADDRESS","PREDICT_PRIVY_PRIVATE_KEY","PREDICT_API_KEY","ERC_MANDATED_VAULT_ADDRESS","ERC_MANDATED_FACTORY_ADDRESS","ERC_MANDATED_VAULT_ASSET_ADDRESS","ERC_MANDATED_VAULT_NAME","ERC_MANDATED_VAULT_SYMBOL","ERC_MANDATED_VAULT_AUTHORITY","ERC_MANDATED_VAULT_SALT","ERC_MANDATED_AUTHORITY_PRIVATE_KEY","ERC_MANDATED_EXECUTOR_PRIVATE_KEY","ERC_MANDATED_MCP_COMMAND","ERC_MANDATED_CONTRACT_VERSION","ERC_MANDATED_CHAIN_ID","ERC_MANDATED_ALLOWED_ADAPTERS_ROOT","ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX","ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW","ERC_MANDATED_FUNDING_WINDOW_SECONDS","OPENROUTER_API_KEY"]},"install":[{"id":"uv-brew","kind":"brew","formula":"uv","bins":["uv"],"label":"Install uv (brew)"}]}}
---

# PredictClaw

PredictClaw is the predict.fun-native OpenClaw skill for browsing markets, checking wallet readiness, viewing deposit addresses, withdrawing funds, placing buys, inspecting positions, and scanning hedge opportunities.

## Install

### ClawHub / packaged install

```bash
clawhub install predictclaw
```

### Manual install

1. Copy or symlink this repository into `~/.openclaw/skills/predictclaw/`
2. From the installed skill directory, run:

```bash
cd {baseDir} && uv sync
```

## OpenClaw config snippets

All examples below belong inside `skills.entries.predictclaw.env`.

`OPENROUTER_API_KEY` appears in the signer examples only for optional `hedge scan` / `hedge analyze` usage; it is not required for market, wallet, or buy flows and is only needed for non-fixture hedge analysis.

### read-only mode

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: read-only
        PREDICT_ENV: testnet
        PREDICT_API_BASE_URL: https://dev.predict.fun
```

### eoa mode

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: eoa
        PREDICT_ENV: testnet
        PREDICT_API_BASE_URL: https://dev.predict.fun
        PREDICT_PRIVATE_KEY: 0xYOUR_EOA_PRIVATE_KEY
        OPENROUTER_API_KEY: sk-or-v1-...
```

### predict-account mode

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: predict-account
        PREDICT_ENV: testnet
        PREDICT_API_BASE_URL: https://dev.predict.fun
        PREDICT_ACCOUNT_ADDRESS: 0xYOUR_PREDICT_ACCOUNT
        PREDICT_PRIVY_PRIVATE_KEY: 0xYOUR_PRIVY_EXPORTED_KEY
        OPENROUTER_API_KEY: sk-or-v1-...
```

### mandated-vault mode (advanced control-plane only)

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: mandated-vault
        PREDICT_ENV: testnet
        ERC_MANDATED_VAULT_ADDRESS: 0xYOUR_DEPLOYED_VAULT
        ERC_MANDATED_AUTHORITY_PRIVATE_KEY: 0xYOUR_VAULT_AUTHORITY_KEY
        ERC_MANDATED_MCP_COMMAND: erc-mandated-mcp
        ERC_MANDATED_CONTRACT_VERSION: v0.3.0-agent-contract
        ERC_MANDATED_CHAIN_ID: "97"
```

`ERC_MANDATED_EXECUTOR_PRIVATE_KEY` is optional. When it is unset, PredictClaw reuses `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` as the executor signer for the current Preflight MVP contract.

If you do **not** have an explicit deployed vault address yet, provide the full derivation tuple instead:

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: mandated-vault
        PREDICT_ENV: testnet
        ERC_MANDATED_FACTORY_ADDRESS: 0xYOUR_FACTORY
        ERC_MANDATED_VAULT_ASSET_ADDRESS: 0xYOUR_ASSET
        ERC_MANDATED_VAULT_NAME: Mandated Vault
        ERC_MANDATED_VAULT_SYMBOL: MVLT
        ERC_MANDATED_VAULT_AUTHORITY: 0xYOUR_AUTHORITY
        ERC_MANDATED_VAULT_SALT: 0xYOUR_SALT
        ERC_MANDATED_MCP_COMMAND: erc-mandated-mcp
        ERC_MANDATED_CONTRACT_VERSION: v0.3.0-agent-contract
        ERC_MANDATED_CHAIN_ID: "97"
```

In that path, PredictClaw asks the MCP to predict the vault address and, when the vault is still undeployed, returns create-vault preparation guidance only. It does **not** auto-broadcast.

### predict-account + vault overlay (recommended advanced funding route)

```yaml
skills:
  entries:
    predictclaw:
      env:
        PREDICT_WALLET_MODE: predict-account
        PREDICT_ENV: testnet
        PREDICT_ACCOUNT_ADDRESS: 0xYOUR_PREDICT_ACCOUNT
        PREDICT_PRIVY_PRIVATE_KEY: 0xYOUR_PRIVY_EXPORTED_KEY
        ERC_MANDATED_VAULT_ADDRESS: 0xYOUR_DEPLOYED_VAULT
        ERC_MANDATED_AUTHORITY_PRIVATE_KEY: 0xYOUR_VAULT_AUTHORITY_KEY
        ERC_MANDATED_FACTORY_ADDRESS: 0xYOUR_FACTORY
        ERC_MANDATED_VAULT_ASSET_ADDRESS: 0xYOUR_ASSET
        ERC_MANDATED_VAULT_NAME: Mandated Vault
        ERC_MANDATED_VAULT_SYMBOL: MVLT
        ERC_MANDATED_VAULT_AUTHORITY: 0xYOUR_AUTHORITY
        ERC_MANDATED_VAULT_SALT: 0xYOUR_SALT
        ERC_MANDATED_MCP_COMMAND: erc-mandated-mcp
        ERC_MANDATED_CONTRACT_VERSION: v0.3.0-agent-contract
        ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX: "5000000000000000000"
        ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW: "10000000000000000000"
        ERC_MANDATED_FUNDING_WINDOW_SECONDS: "3600"
```

In the overlay route, Predict Account remains the deposit/trading account while Vault funds the Predict Account through MCP-backed session and asset-transfer planning.
The optional `ERC_MANDATED_FUNDING_*` envs cap Vault→Predict transfers by per-tx amount, per-window cumulative amount, and window duration. On BSC mainnet USDT, `5U = 5000000000000000000` and `10U = 10000000000000000000`.

## Wallet-mode contract

- `read-only` — browse market data only; no signer-backed wallet actions.
- `eoa` — direct signer path for wallet, trade, and funding flows.
- `predict-account` — smart-wallet funding/trading path using `PREDICT_ACCOUNT_ADDRESS` plus `PREDICT_PRIVY_PRIVATE_KEY`.
- `mandated-vault` — advanced explicit opt-in control-plane path for protected vault-only status/deposit flows.

## First-time setup

- Default local posture is `test-fixture` or `testnet`.
- `mainnet` requires `PREDICT_API_KEY`.
- `wallet deposit` shows the funding address for the active signer mode.
- `wallet withdraw` performs safety validation before any transfer logic.
- In pure `mandated-vault`, `wallet status` and `wallet deposit` are the intended v1 entry points.
- In `predict-account + ERC_MANDATED_*` overlay, `wallet status` / `wallet deposit` expose `vault-to-predict-account` funding semantics while Predict Account remains the trade identity.
- Overlay `buy` can proceed when the Predict Account balance is sufficient; otherwise it returns deterministic `funding-required` guidance that points to `wallet deposit --json`.
- Hedge analysis uses OpenRouter; `OPENROUTER_API_KEY` is only required for non-fixture hedge analysis, and fixture mode stays secret-free.

```bash
cd {baseDir} && uv run python scripts/predictclaw.py --help
cd {baseDir} && uv run python scripts/predictclaw.py wallet status --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet deposit --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw usdt 1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
```

## Command surface

```bash
cd {baseDir} && uv run python scripts/predictclaw.py markets trending
cd {baseDir} && uv run python scripts/predictclaw.py markets search "election"
cd {baseDir} && uv run python scripts/predictclaw.py market 123 --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet status --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet approve --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet deposit --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw usdt 1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
cd {baseDir} && uv run python scripts/predictclaw.py wallet withdraw bnb 0.1 0xb30741673D351135Cf96564dfD15f8e135f9C310 --json
cd {baseDir} && uv run python scripts/predictclaw.py buy 123 YES 25 --json
cd {baseDir} && uv run python scripts/predictclaw.py positions --json
cd {baseDir} && uv run python scripts/predictclaw.py position pos-123-yes --json
cd {baseDir} && uv run python scripts/predictclaw.py hedge scan --query election --json
cd {baseDir} && uv run python scripts/predictclaw.py hedge analyze 101 202 --json
```

## Environment variables

| Variable | Purpose |
| --- | --- |
| `PREDICT_STORAGE_DIR` | Local journal and position storage |
| `PREDICT_ENV` | Defaults to `testnet`; accepted values are `testnet`, `mainnet`, or `test-fixture` |
| `PREDICT_WALLET_MODE` | Explicit mode override: `read-only`, `eoa`, `predict-account`, or `mandated-vault` |
| `PREDICT_API_BASE_URL` | Optional REST base override |
| `PREDICT_API_KEY` | Mainnet-authenticated predict.fun API access |
| `PREDICT_PRIVATE_KEY` | EOA trading and funding path |
| `PREDICT_ACCOUNT_ADDRESS` | Predict Account smart-wallet address |
| `PREDICT_PRIVY_PRIVATE_KEY` | Privy-exported signer for Predict Account mode |
| `ERC_MANDATED_VAULT_ADDRESS` | Explicit deployed mandated vault address |
| `ERC_MANDATED_FACTORY_ADDRESS` | Factory address used to predict a vault when no explicit vault address is supplied |
| `ERC_MANDATED_VAULT_ASSET_ADDRESS` | ERC-4626 asset used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_NAME` | Vault name used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_SYMBOL` | Vault symbol used in mandated-vault prediction/create preparation |
| `ERC_MANDATED_VAULT_AUTHORITY` | Authority address and create-vault `from` address for manual preparation |
| `ERC_MANDATED_VAULT_SALT` | Deterministic salt used for vault prediction/create preparation |
| `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` | Preflight Vault signer key for the current single-key MVP contract |
| `ERC_MANDATED_EXECUTOR_PRIVATE_KEY` | Optional dedicated executor signer; falls back to `ERC_MANDATED_AUTHORITY_PRIVATE_KEY` when unset |
| `ERC_MANDATED_MCP_COMMAND` | MCP launcher command (defaults to `erc-mandated-mcp`) |
| `ERC_MANDATED_CONTRACT_VERSION` | Passed through to the mandated-vault MCP client |
| `ERC_MANDATED_CHAIN_ID` | Optional explicit chain selection for the MCP bridge |
| `ERC_MANDATED_ALLOWED_ADAPTERS_ROOT` | Optional 32-byte hex `allowedAdaptersRoot` used for Vault execution mandates; defaults to `0x11…11` for the current single-key MVP / PoC path |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_TX` | Optional Vault→Predict funding-policy `maxAmountPerTx` in raw token units |
| `ERC_MANDATED_FUNDING_MAX_AMOUNT_PER_WINDOW` | Optional Vault→Predict funding-policy `maxAmountPerWindow` in raw token units |
| `ERC_MANDATED_FUNDING_WINDOW_SECONDS` | Optional Vault→Predict funding-policy `windowSeconds` |
| `OPENROUTER_API_KEY` | Optional OpenRouter credential; only required for non-fixture hedge analysis |
| `PREDICT_MODEL` | OpenRouter model override |
| `PREDICT_SMOKE_ENV` | Enables the smoke suite |
| `PREDICT_SMOKE_API_BASE_URL` | Optional smoke REST base override |
| `PREDICT_SMOKE_PRIVATE_KEY` | Enables signer/JWT smoke checks |
| `PREDICT_SMOKE_ACCOUNT_ADDRESS` | Predict Account smoke mode |
| `PREDICT_SMOKE_PRIVY_PRIVATE_KEY` | Predict Account smoke signer |
| `PREDICT_SMOKE_API_KEY` | Smoke REST auth |

## Architecture note

- **SDK for chain-aware/signed flows**
- **REST for auth, data, order submission, and query**

## Safety notes

- Do not treat fixture mode as proof of funded-wallet behavior.
- Do not assume live liquidity from testnet or mainnet docs alone.
- Keep only limited funds on automation keys.
- Withdrawal commands are public; transfer validation happens before chain interaction, but users still own the operational risk.
- `mandated-vault` is an advanced explicit opt-in mode. Only enable it when you intentionally want MCP-assisted vault control-plane behavior.
- `predict-account + ERC_MANDATED_*` is the recommended advanced trading route when you want Vault to fund the Predict Account while keeping the official Predict Account order model.
- Explicit-vs-predicted vault semantics: `ERC_MANDATED_VAULT_ADDRESS` targets an existing vault directly; otherwise PredictClaw uses the derivation tuple to ask the MCP for the predicted vault address.
- If a predicted vault is undeployed, `wallet deposit` can return create-vault preparation details (`predictedVault`, transaction summary, `manual-only`) without broadcasting.
- Trust boundary: the MCP orchestrates transport and preparation; the vault contract policy authorizes what the vault can actually execute.
- Pure `mandated-vault` does not provide predict.fun trading parity. `wallet approve`, `wallet withdraw`, `buy`, `positions`, `position`, `hedge scan`, and `hedge analyze` fail closed with `unsupported-in-mandated-vault-v1`.
- Overlay funding currently plans the vault leg and surfaces deterministic `funding-required` guidance when buy needs top-up; it does not auto-execute the funding leg in the current local signer context.
