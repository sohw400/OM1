import time
from unittest.mock import Mock, patch

import pytest

from inputs.base import SensorConfig
from inputs.plugins.wallet_base import WalletBalance
from inputs.plugins.wallet_universal import Message, WalletUniversal


@pytest.fixture
def mock_io_provider():
    with patch("inputs.plugins.wallet_universal.IOProvider") as mock:
        mock_instance = Mock()
        mock.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def mock_adapter_factory():
    with patch("inputs.plugins.wallet_universal.AdapterFactory") as mock:
        yield mock


@pytest.fixture
def wallet_config():
    config = SensorConfig()
    config.wallet_address = "0x742d35Cc6634C0532925a3b844Bc9e7595f0bEb"
    config.chains = ["ethereum", "polygon"]
    config.poll_interval = 10
    config.mock_mode = False
    return config


@pytest.fixture
def mock_wallet_config():
    config = SensorConfig()
    config.mock_mode = True
    config.chains = ["ethereum", "polygon", "solana"]
    config.poll_interval = 5
    return config


@pytest.fixture
def wallet_universal(wallet_config, mock_io_provider, mock_adapter_factory):
    mock_eth_adapter = Mock()
    mock_eth_adapter.validate_address.return_value = True
    mock_poly_adapter = Mock()
    mock_poly_adapter.validate_address.return_value = True

    mock_adapter_factory.create_adapter.side_effect = [
        mock_eth_adapter,
        mock_poly_adapter
    ]

    return WalletUniversal(wallet_config)


@pytest.fixture
def mock_wallet_universal(mock_wallet_config, mock_io_provider, mock_adapter_factory):
    return WalletUniversal(mock_wallet_config)


def test_init_with_address(wallet_universal, wallet_config):
    assert wallet_universal.wallet_address == wallet_config.wallet_address
    assert wallet_universal.enabled_chains == ["ethereum", "polygon"]
    assert wallet_universal.poll_interval == 10
    assert wallet_universal.mock_mode is False
    assert len(wallet_universal.adapters) == 2
    assert isinstance(wallet_universal.messages, list)


def test_init_mock_mode(mock_wallet_universal):
    assert mock_wallet_universal.mock_mode is True
    assert mock_wallet_universal.wallet_address == "0xMOCK_ADDRESS"
    assert "ethereum" in mock_wallet_universal.enabled_chains
    assert "solana" in mock_wallet_universal.enabled_chains


def test_init_no_address(mock_io_provider, mock_adapter_factory):
    config = SensorConfig()
    config.mock_mode = False
    wallet = WalletUniversal(config)
    assert wallet.wallet_address is None


@pytest.mark.asyncio
async def test_connect_success(wallet_universal):
    result = await wallet_universal.connect()
    assert result is True
    assert wallet_universal.connected is True


@pytest.mark.asyncio
async def test_connect_mock_mode(mock_wallet_universal):
    result = await mock_wallet_universal.connect()
    assert result is True
    assert mock_wallet_universal.connected is True


@pytest.mark.asyncio
async def test_connect_no_address(mock_io_provider, mock_adapter_factory):
    config = SensorConfig()
    config.mock_mode = False
    wallet = WalletUniversal(config)

    result = await wallet.connect()
    assert result is False


@pytest.mark.asyncio
async def test_disconnect(wallet_universal):
    await wallet_universal.connect()
    await wallet_universal.disconnect()

    assert wallet_universal.connected is False
    assert len(wallet_universal.adapters) == 0


@pytest.mark.asyncio
async def test_get_balance_real_mode(wallet_universal):
    mock_balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)

    mock_adapter = Mock()
    mock_adapter.get_balance.return_value = mock_balance
    wallet_universal.adapters["ethereum"] = mock_adapter

    result = await wallet_universal.get_balance("ethereum", "native")

    assert result == mock_balance
    assert result.chain == "ethereum"
    assert result.amount == 1.5
    mock_adapter.get_balance.assert_called_once()


@pytest.mark.asyncio
async def test_get_balance_mock_mode(mock_wallet_universal):
    result = await mock_wallet_universal.get_balance("ethereum", "native")

    assert result is not None
    assert result.chain == "ethereum"
    assert result.asset == "ETH"
    assert result.amount > 0


@pytest.mark.asyncio
async def test_get_balance_no_adapter(wallet_universal):
    result = await wallet_universal.get_balance("bitcoin", "native")
    assert result is None


@pytest.mark.asyncio
async def test_get_all_balances(wallet_universal):
    eth_balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)
    poly_balance = WalletBalance(chain="polygon", asset="MATIC", amount=500.0)

    mock_eth_adapter = Mock()
    mock_eth_adapter.get_balance.return_value = eth_balance
    mock_poly_adapter = Mock()
    mock_poly_adapter.get_balance.return_value = poly_balance

    wallet_universal.adapters["ethereum"] = mock_eth_adapter
    wallet_universal.adapters["polygon"] = mock_poly_adapter

    result = await wallet_universal.get_all_balances()

    assert len(result) == 2
    assert eth_balance in result
    assert poly_balance in result


@pytest.mark.asyncio
async def test_get_all_balances_filters_zero(wallet_universal):
    eth_balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)
    poly_balance = WalletBalance(chain="polygon", asset="MATIC", amount=0.0)

    mock_eth_adapter = Mock()
    mock_eth_adapter.get_balance.return_value = eth_balance
    mock_poly_adapter = Mock()
    mock_poly_adapter.get_balance.return_value = poly_balance

    wallet_universal.adapters["ethereum"] = mock_eth_adapter
    wallet_universal.adapters["polygon"] = mock_poly_adapter

    result = await wallet_universal.get_all_balances()

    assert len(result) == 1
    assert eth_balance in result
    assert poly_balance not in result


@pytest.mark.asyncio
async def test_get_recent_transactions_real_mode(wallet_universal):
    mock_adapter = Mock()
    mock_adapter.get_transactions.return_value = []
    wallet_universal.adapters["ethereum"] = mock_adapter

    result = await wallet_universal.get_recent_transactions("ethereum", 5)

    assert result == []
    mock_adapter.get_transactions.assert_called_once_with(
        wallet_universal.wallet_address, 5
    )


@pytest.mark.asyncio
async def test_get_recent_transactions_mock_mode(mock_wallet_universal):
    result = await mock_wallet_universal.get_recent_transactions("ethereum", 10)
    assert result == []


def test_get_mock_balance_ethereum(mock_wallet_universal):
    result = mock_wallet_universal._get_mock_balance("ethereum", "native")

    assert result.chain == "ethereum"
    assert result.asset == "ETH"
    assert 1.4 <= result.amount <= 1.6


def test_get_mock_balance_solana(mock_wallet_universal):
    result = mock_wallet_universal._get_mock_balance("solana", "native")

    assert result.chain == "solana"
    assert result.asset == "SOL"
    assert 9.9 <= result.amount <= 10.1


def test_get_mock_balance_polygon(mock_wallet_universal):
    result = mock_wallet_universal._get_mock_balance("polygon", "native")

    assert result.chain == "polygon"
    assert result.asset == "MATIC"
    assert 499.9 <= result.amount <= 500.1


@pytest.mark.asyncio
async def test_poll_no_changes(wallet_universal):
    eth_balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)

    mock_adapter = Mock()
    mock_adapter.get_balance.return_value = eth_balance
    wallet_universal.adapters["ethereum"] = mock_adapter
    wallet_universal.adapters["polygon"] = Mock()
    wallet_universal.adapters["polygon"].get_balance.return_value = None

    # Set previous balance to same value
    wallet_universal.previous_balances["ethereum_ETH"] = 1.5

    result = await wallet_universal._poll()

    assert result == {}


@pytest.mark.asyncio
async def test_poll_with_changes(wallet_universal):
    eth_balance = WalletBalance(chain="ethereum", asset="ETH", amount=2.0)

    mock_adapter = Mock()
    mock_adapter.get_balance.return_value = eth_balance
    wallet_universal.adapters["ethereum"] = mock_adapter
    wallet_universal.adapters["polygon"] = Mock()
    wallet_universal.adapters["polygon"].get_balance.return_value = None

    # Set previous balance to different value
    wallet_universal.previous_balances["ethereum_ETH"] = 1.5

    result = await wallet_universal._poll()

    assert "ethereum" in result
    assert len(result["ethereum"]) == 1
    assert result["ethereum"][0].amount == 2.0
    assert wallet_universal.previous_balances["ethereum_ETH"] == 2.0


@pytest.mark.asyncio
async def test_raw_to_text_with_changes(wallet_universal):
    changes = {
        "ethereum": [WalletBalance(chain="ethereum", asset="ETH", amount=1.5)],
        "polygon": [WalletBalance(chain="polygon", asset="MATIC", amount=500.0)]
    }

    result = await wallet_universal._raw_to_text(changes)

    assert result is not None
    assert isinstance(result, Message)
    assert "Ethereum" in result.message
    assert "1.5000 ETH" in result.message
    assert "Polygon" in result.message
    assert "500.0000 MATIC" in result.message


@pytest.mark.asyncio
async def test_raw_to_text_no_changes(wallet_universal):
    result = await wallet_universal._raw_to_text({})
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_zero_balance(wallet_universal):
    changes = {
        "ethereum": [WalletBalance(chain="ethereum", asset="ETH", amount=0.0)]
    }

    result = await wallet_universal._raw_to_text(changes)
    assert result is None


@pytest.mark.asyncio
async def test_raw_to_text_buffer_management(wallet_universal):
    changes = {
        "ethereum": [WalletBalance(chain="ethereum", asset="ETH", amount=1.5)]
    }

    await wallet_universal.raw_to_text(changes)

    assert len(wallet_universal.messages) == 1
    assert isinstance(wallet_universal.messages[0], Message)


def test_formatted_latest_buffer_with_messages(wallet_universal):
    current_time = time.time()
    test_message = Message(
        timestamp=current_time,
        message="Your Ethereum wallet balance is now 1.5000 ETH."
    )
    wallet_universal.messages = [test_message]

    result = wallet_universal.formatted_latest_buffer()

    assert result is not None
    assert "INPUT: Wallet" in result
    assert "START" in result
    assert "END" in result
    assert "1.5000 ETH" in result
    assert len(wallet_universal.messages) == 0
    wallet_universal.io_provider.add_input.assert_called_once()


def test_formatted_latest_buffer_empty(wallet_universal):
    result = wallet_universal.formatted_latest_buffer()
    assert result is None
    wallet_universal.io_provider.add_input.assert_not_called()


def test_get_supported_chains(wallet_universal):
    chains = wallet_universal.get_supported_chains()

    assert isinstance(chains, list)
    assert "ethereum" in chains
    assert "polygon" in chains
    assert "solana" in chains
    assert "bsc" in chains
    assert "arbitrum" in chains
    assert "optimism" in chains


def test_get_supported_wallets(wallet_universal):
    wallets = wallet_universal.get_supported_wallets()

    assert isinstance(wallets, list)
    assert "MetaMask" in wallets
    assert "Phantom" in wallets
    assert "Trust Wallet" in wallets
    assert "Ledger" in wallets
    assert any("300+" in w for w in wallets)
