from unittest.mock import Mock, patch

import pytest

from inputs.plugins.wallet_adapters import (
    AdapterFactory,
    EthereumAdapter,
    SolanaAdapter,
)
from inputs.plugins.wallet_base import WalletBalance


@pytest.fixture
def mock_web3():
    with patch("inputs.plugins.wallet_adapters.Web3") as mock:
        mock_instance = Mock()
        mock_http_provider = Mock()
        mock.HTTPProvider.return_value = mock_http_provider
        mock.return_value = mock_instance
        mock_instance.is_connected.return_value = True
        mock_instance.from_wei = lambda wei, unit: float(wei) / 1e18
        mock_instance.eth = Mock()
        mock_instance.is_address.return_value = True
        yield mock_instance


def test_ethereum_adapter_init_default(mock_web3):
    adapter = EthereumAdapter()

    assert adapter.chain_id == "ethereum"
    assert adapter.rpc_url == "https://eth.llamarpc.com"
    assert adapter.web3 is not None
    mock_web3.is_connected.assert_called_once()


def test_ethereum_adapter_init_polygon(mock_web3):
    adapter = EthereumAdapter(chain_name="polygon")

    assert adapter.chain_id == "polygon"
    assert adapter.rpc_url == "https://polygon-rpc.com"


def test_ethereum_adapter_init_custom_rpc(mock_web3):
    custom_rpc = "https://custom-rpc.example.com"
    adapter = EthereumAdapter(rpc_url=custom_rpc)

    assert adapter.rpc_url == custom_rpc


def test_ethereum_adapter_init_connection_failed(mock_web3):
    mock_web3.is_connected.return_value = False
    adapter = EthereumAdapter()

    assert adapter.web3 is not None


def test_ethereum_adapter_init_no_web3():
    with patch("inputs.plugins.wallet_adapters.Web3", side_effect=ImportError):
        adapter = EthereumAdapter()
        assert adapter.web3 is None


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_eth(mock_web3):
    adapter = EthereumAdapter()
    test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

    mock_web3.eth.get_balance.return_value = 1500000000000000000  # 1.5 ETH

    result = await adapter.get_balance(test_address, "native")

    assert result is not None
    assert isinstance(result, WalletBalance)
    assert result.chain == "ethereum"
    assert result.asset == "ETH"
    assert result.amount == 1.5
    mock_web3.eth.get_balance.assert_called_once_with(test_address)


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_polygon(mock_web3):
    adapter = EthereumAdapter(chain_name="polygon")
    test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

    mock_web3.eth.get_balance.return_value = 500000000000000000000  # 500 MATIC

    result = await adapter.get_balance(test_address, "native")

    assert result is not None
    assert result.chain == "polygon"
    assert result.asset == "MATIC"
    assert result.amount == 500.0


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_bsc(mock_web3):
    adapter = EthereumAdapter(chain_name="bsc")
    test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

    mock_web3.eth.get_balance.return_value = 500000000000000000  # 0.5 BNB

    result = await adapter.get_balance(test_address, "native")

    assert result is not None
    assert result.chain == "bsc"
    assert result.asset == "BNB"
    assert result.amount == 0.5


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_arbitrum(mock_web3):
    adapter = EthereumAdapter(chain_name="arbitrum")
    test_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"

    mock_web3.eth.get_balance.return_value = 800000000000000000  # 0.8 ETH

    result = await adapter.get_balance(test_address, "native")

    assert result is not None
    assert result.chain == "arbitrum"
    assert result.asset == "ETH"
    assert result.amount == 0.8


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_no_web3(mock_web3):
    adapter = EthereumAdapter()
    adapter.web3 = None

    result = await adapter.get_balance("0xtest", "native")
    assert result is None


@pytest.mark.asyncio
async def test_ethereum_adapter_get_balance_error(mock_web3):
    adapter = EthereumAdapter()
    mock_web3.eth.get_balance.side_effect = Exception("RPC error")

    result = await adapter.get_balance("0xtest", "native")
    assert result is None


@pytest.mark.asyncio
async def test_ethereum_adapter_get_transactions(mock_web3):
    adapter = EthereumAdapter()

    result = await adapter.get_transactions("0xtest", 10)

    assert isinstance(result, list)
    assert len(result) == 0


def test_ethereum_adapter_validate_address_valid(mock_web3):
    adapter = EthereumAdapter()
    mock_web3.is_address.return_value = True

    result = adapter.validate_address("0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb")

    assert result is True
    mock_web3.is_address.assert_called_once()


def test_ethereum_adapter_validate_address_invalid(mock_web3):
    adapter = EthereumAdapter()
    mock_web3.is_address.return_value = False

    result = adapter.validate_address("invalid_address")

    assert result is False


def test_ethereum_adapter_validate_address_no_web3():
    with patch("inputs.plugins.wallet_adapters.Web3", side_effect=ImportError):
        adapter = EthereumAdapter()
        result = adapter.validate_address("0xtest")
        assert result is False


def test_solana_adapter_init():
    adapter = SolanaAdapter()

    assert adapter.chain_id == "solana"
    assert adapter.rpc_url == "https://api.mainnet-beta.solana.com"
    assert adapter.client is None


def test_solana_adapter_init_custom_rpc():
    custom_rpc = "https://custom-solana-rpc.com"
    adapter = SolanaAdapter(rpc_url=custom_rpc)

    assert adapter.rpc_url == custom_rpc


@pytest.mark.asyncio
async def test_solana_adapter_get_balance():
    adapter = SolanaAdapter()
    test_address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"

    result = await adapter.get_balance(test_address, "native")

    # Currently returns None as implementation is pending
    assert result is None


@pytest.mark.asyncio
async def test_solana_adapter_get_transactions():
    adapter = SolanaAdapter()

    result = await adapter.get_transactions("DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK", 5)

    assert isinstance(result, list)
    assert len(result) == 0


def test_solana_adapter_validate_address_valid():
    adapter = SolanaAdapter()

    valid_address = "DYw8jCTfwHNRJhhmFcbXvVDTqWMEVFBX6ZKUmG5CNSKK"
    result = adapter.validate_address(valid_address)

    assert result is True


def test_solana_adapter_validate_address_too_short():
    adapter = SolanaAdapter()

    result = adapter.validate_address("tooshort")

    assert result is False


def test_solana_adapter_validate_address_too_long():
    adapter = SolanaAdapter()

    too_long = "a" * 50
    result = adapter.validate_address(too_long)

    assert result is False


def test_solana_adapter_validate_address_empty():
    adapter = SolanaAdapter()

    result = adapter.validate_address("")

    assert result is False


def test_adapter_factory_create_ethereum():
    adapter = AdapterFactory.create_adapter("ethereum")

    assert adapter is not None
    assert isinstance(adapter, EthereumAdapter)
    assert adapter.chain_id == "ethereum"


def test_adapter_factory_create_polygon():
    adapter = AdapterFactory.create_adapter("polygon")

    assert adapter is not None
    assert isinstance(adapter, EthereumAdapter)
    assert adapter.chain_id == "polygon"


def test_adapter_factory_create_bsc():
    adapter = AdapterFactory.create_adapter("bsc")

    assert adapter is not None
    assert isinstance(adapter, EthereumAdapter)
    assert adapter.chain_id == "bsc"


def test_adapter_factory_create_arbitrum():
    adapter = AdapterFactory.create_adapter("arbitrum")

    assert adapter is not None
    assert isinstance(adapter, EthereumAdapter)
    assert adapter.chain_id == "arbitrum"


def test_adapter_factory_create_optimism():
    adapter = AdapterFactory.create_adapter("optimism")

    assert adapter is not None
    assert isinstance(adapter, EthereumAdapter)
    assert adapter.chain_id == "optimism"


def test_adapter_factory_create_solana():
    adapter = AdapterFactory.create_adapter("solana")

    assert adapter is not None
    assert isinstance(adapter, SolanaAdapter)
    assert adapter.chain_id == "solana"


def test_adapter_factory_create_custom_rpc():
    custom_rpc = "https://custom.rpc.url"
    adapter = AdapterFactory.create_adapter("ethereum", rpc_url=custom_rpc)

    assert adapter is not None
    assert adapter.rpc_url == custom_rpc


def test_adapter_factory_create_unsupported():
    adapter = AdapterFactory.create_adapter("bitcoin")

    assert adapter is None


def test_adapter_factory_get_supported_chains():
    chains = AdapterFactory.get_supported_chains()

    assert isinstance(chains, list)
    assert "ethereum" in chains
    assert "polygon" in chains
    assert "bsc" in chains
    assert "arbitrum" in chains
    assert "optimism" in chains
    assert "solana" in chains
    assert len(chains) == 6
