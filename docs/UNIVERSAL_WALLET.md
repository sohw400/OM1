# Universal Multi-Wallet Support

OM1's Universal Wallet implementation provides support for 300+ cryptocurrency wallets through a unified, wallet-agnostic architecture.

## Overview

Instead of implementing separate connectors for each wallet, the Universal Wallet uses **chain adapters** that work with any wallet supporting standard blockchain RPCs. This means:

- ✅ **300+ wallets supported** automatically
- ✅ **Multi-chain** support (Ethereum, Solana, Polygon, BSC, etc.)
- ✅ **Zero code changes** to add new wallets
- ✅ **Easy to extend** with new blockchains

## Supported Wallets

The Universal Wallet works with any wallet that supports blockchain RPC connections:

### Ethereum & EVM Chains
- MetaMask
- Trust Wallet
- Coinbase Wallet
- Rainbow Wallet
- Argent
- Safe (Gnosis Safe)
- Ledger (hardware)
- Trezor (hardware)
- **And 200+ more via WalletConnect**

### Solana
- Phantom
- Solflare
- Backpack
- Ledger (hardware)
- **And 50+ more**

### Multi-Chain
- WalletConnect v2 (supports 300+ wallets)
- Ledger (multi-chain hardware wallet)
- Any wallet with RPC support

## Supported Blockchains

- **Ethereum** (ETH)
- **Polygon** (MATIC)
- **Binance Smart Chain** (BNB)
- **Arbitrum** (ETH L2)
- **Optimism** (ETH L2)
- **Solana** (SOL)

Additional chains can be added easily by creating new adapters.

## Configuration

### Basic Setup

```json
{
  "agent_inputs": [
    {
      "type": "WalletUniversal",
      "config": {
        "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
        "chains": ["ethereum", "polygon"],
        "poll_interval": 10
      }
    }
  ]
}
```

### Configuration Options

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `wallet_address` | string | required | Wallet address to monitor |
| `chains` | list | `["ethereum"]` | Chains to monitor |
| `poll_interval` | int | 10 | Seconds between balance checks |
| `mock_mode` | bool | false | Use simulated data for testing |

### Multi-Chain Example

```json
{
  "type": "WalletUniversal",
  "config": {
    "wallet_address": "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb",
    "chains": ["ethereum", "polygon", "arbitrum", "optimism"],
    "poll_interval": 15
  }
}
```

### Solana Example

```json
{
  "type": "WalletUniversal",
  "config": {
    "wallet_address": "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK",
    "chains": ["solana"],
    "poll_interval": 10
  }
}
```

## Usage

### Monitoring Balance Changes

The Universal Wallet automatically detects balance changes and notifies the agent in natural language:

```
Your Ethereum wallet balance is now 1.5432 ETH.
Your Polygon wallet balance is now 523.45 MATIC.
```

### Mock Mode for Testing

Test without a real wallet:

```json
{
  "type": "WalletUniversal",
  "config": {
    "mock_mode": true,
    "chains": ["ethereum", "polygon", "solana"]
  }
}
```

Mock mode generates realistic balance variations for development and testing.

## Architecture

### Component Overview

```
WalletUniversal (Main class)
    ↓
ChainAdapters (Blockchain-specific logic)
    ↓
RPC Endpoints (Blockchain networks)
    ↓
Wallet (Any wallet supporting RPC)
```

### Adding a New Chain

To add support for a new blockchain:

1. Create a new adapter class:

```python
class NewChainAdapter(ChainAdapter):
    def __init__(self, rpc_url=None):
        super().__init__(rpc_url or "https://rpc.newchain.com")
        self.chain_id = "newchain"

    async def get_balance(self, address, asset="native"):
        # Implementation
        pass

    async def get_transactions(self, address, limit=10):
        # Implementation
        pass

    def validate_address(self, address):
        # Address validation
        pass
```

2. Register in `AdapterFactory`:

```python
elif chain == "newchain":
    return NewChainAdapter(rpc_url=rpc_url)
```

3. Add to supported chains list:

```python
SUPPORTED_CHAINS = [..., "newchain"]
```

That's it! The new chain is now supported.

## API Reference

### WalletUniversal Class

#### Methods

**`async connect() -> bool`**
- Validates wallet address and initializes chain adapters
- Returns `True` if successful

**`async disconnect()`**
- Cleans up resources and disconnects

**`async get_balance(chain: str, asset: str) -> Optional[WalletBalance]`**
- Gets balance for specific chain and asset
- Returns balance information or `None`

**`async get_all_balances() -> List[WalletBalance]`**
- Gets balances across all configured chains
- Returns list of non-zero balances

**`get_supported_chains() -> List[str]`**
- Returns list of supported blockchain identifiers

**`get_supported_wallets() -> List[str]`**
- Returns list of compatible wallet names

### WalletBalance Dataclass

```python
@dataclass
class WalletBalance:
    chain: str           # e.g., "ethereum"
    asset: str           # e.g., "ETH"
    amount: float        # Balance amount
    usd_value: Optional[float]  # USD value if available
```

## Comparison with Other Implementations

| Feature | Universal Wallet | Single Wallet Impl |
|---------|------------------|-------------------|
| Wallets supported | 300+ | 1 |
| Code maintenance | Low | High per wallet |
| New wallet support | Automatic | Manual coding |
| Multi-chain | ✅ Yes | ❌ Usually no |
| Extensibility | ✅ High | ❌ Limited |

## Security Considerations

### Address Validation
- All addresses are validated before use
- Chain-specific format checking

### RPC Endpoints
- Uses public RPC endpoints by default
- Can configure custom endpoints for privacy
- No private keys are stored or transmitted

### Read-Only Operations
- Only queries blockchain state
- No transaction signing
- No access to wallet private keys

## Troubleshooting

**No balance showing:**
- Verify wallet address is correct for the chain
- Check RPC endpoint is accessible
- Enable debug logging to see detailed errors

**Wrong chain:**
- Ensure wallet address format matches chain
- Ethereum addresses work on all EVM chains
- Solana addresses are different format

**Performance issues:**
- Increase `poll_interval` to reduce RPC calls
- Monitor fewer chains if not needed
- Consider using dedicated RPC endpoints

## Examples

### Ethereum NFT Collector

```json
{
  "system_prompt": "You monitor a wallet and get excited when new NFTs arrive.",
  "agent_inputs": [{
    "type": "WalletUniversal",
    "config": {
      "wallet_address": "0x...",
      "chains": ["ethereum"],
      "poll_interval": 30
    }
  }]
}
```

### Multi-Chain DeFi Tracker

```json
{
  "system_prompt": "Track DeFi positions across multiple chains.",
  "agent_inputs": [{
    "type": "WalletUniversal",
    "config": {
      "wallet_address": "0x...",
      "chains": ["ethereum", "polygon", "arbitrum", "optimism"],
      "poll_interval": 60
    }
  }]
}
```

## Related Issues

- Issue #358: Extend the platform to support multiple wallet providers

## Future Enhancements

- [ ] Token balance tracking (ERC20, SPL)
- [ ] NFT detection and notifications
- [ ] Transaction signing support
- [ ] Price data integration (USD values)
- [ ] Historical balance tracking
- [ ] Gas price monitoring

## License

This feature is part of OM1 and is released under the MIT License.
