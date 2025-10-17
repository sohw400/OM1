import pytest

from inputs.base import SensorConfig
from inputs.plugins.wallet_base import WalletBalance, WalletBase, WalletTransaction


class TestWalletImplementation(WalletBase):
    """
    Concrete implementation of WalletBase for testing purposes.
    """

    async def connect(self) -> bool:
        self.connected = True
        return True

    async def disconnect(self):
        self.connected = False

    async def get_balance(self, chain: str, asset: str = "native"):
        return WalletBalance(chain=chain, asset=asset, amount=1.5)

    async def get_all_balances(self):
        return [
            WalletBalance(chain="ethereum", asset="ETH", amount=1.5),
            WalletBalance(chain="polygon", asset="MATIC", amount=500.0),
        ]

    async def get_recent_transactions(self, chain: str, limit: int = 10):
        return [
            WalletTransaction(
                tx_hash="0xabc123",
                from_address="0x111",
                to_address="0x222",
                value=1.0,
                asset="ETH",
                timestamp=1234567890,
            )
        ]

    async def _poll(self):
        return {"test": "data"}

    async def _raw_to_text(self, raw_input):
        return f"Test output: {raw_input}"


@pytest.fixture
def wallet_config():
    return SensorConfig()


@pytest.fixture
def test_wallet(wallet_config):
    return TestWalletImplementation(wallet_config)


def test_wallet_balance_dataclass():
    balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)

    assert balance.chain == "ethereum"
    assert balance.asset == "ETH"
    assert balance.amount == 1.5
    assert balance.usd_value is None


def test_wallet_balance_with_usd():
    balance = WalletBalance(
        chain="ethereum", asset="ETH", amount=1.5, usd_value=3000.0
    )

    assert balance.usd_value == 3000.0


def test_wallet_transaction_dataclass():
    tx = WalletTransaction(
        tx_hash="0xabc123",
        from_address="0x111",
        to_address="0x222",
        value=1.0,
        asset="ETH",
        timestamp=1234567890,
    )

    assert tx.tx_hash == "0xabc123"
    assert tx.from_address == "0x111"
    assert tx.to_address == "0x222"
    assert tx.value == 1.0
    assert tx.asset == "ETH"
    assert tx.timestamp == 1234567890


def test_wallet_base_init(test_wallet, wallet_config):
    assert test_wallet.config == wallet_config
    assert test_wallet.connected is False


@pytest.mark.asyncio
async def test_wallet_base_connect(test_wallet):
    result = await test_wallet.connect()

    assert result is True
    assert test_wallet.connected is True


@pytest.mark.asyncio
async def test_wallet_base_disconnect(test_wallet):
    await test_wallet.connect()
    await test_wallet.disconnect()

    assert test_wallet.connected is False


@pytest.mark.asyncio
async def test_wallet_base_get_balance(test_wallet):
    balance = await test_wallet.get_balance("ethereum", "native")

    assert balance is not None
    assert balance.chain == "ethereum"
    assert balance.asset == "native"
    assert balance.amount == 1.5


@pytest.mark.asyncio
async def test_wallet_base_get_all_balances(test_wallet):
    balances = await test_wallet.get_all_balances()

    assert len(balances) == 2
    assert balances[0].chain == "ethereum"
    assert balances[1].chain == "polygon"


@pytest.mark.asyncio
async def test_wallet_base_get_recent_transactions(test_wallet):
    transactions = await test_wallet.get_recent_transactions("ethereum", 5)

    assert len(transactions) == 1
    assert transactions[0].tx_hash == "0xabc123"
    assert transactions[0].value == 1.0


@pytest.mark.asyncio
async def test_wallet_base_poll(test_wallet):
    result = await test_wallet._poll()

    assert result == {"test": "data"}


@pytest.mark.asyncio
async def test_wallet_base_raw_to_text(test_wallet):
    result = await test_wallet._raw_to_text("input")

    assert result == "Test output: input"


def test_wallet_base_abstract_methods():
    """
    Verify that WalletBase is properly abstract.
    """
    with pytest.raises(TypeError):
        # Should not be able to instantiate abstract class directly
        WalletBase(SensorConfig())


def test_wallet_balance_equality():
    balance1 = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)
    balance2 = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)
    balance3 = WalletBalance(chain="polygon", asset="MATIC", amount=500.0)

    assert balance1 == balance2
    assert balance1 != balance3


def test_wallet_transaction_equality():
    tx1 = WalletTransaction(
        tx_hash="0xabc",
        from_address="0x111",
        to_address="0x222",
        value=1.0,
        asset="ETH",
        timestamp=123,
    )
    tx2 = WalletTransaction(
        tx_hash="0xabc",
        from_address="0x111",
        to_address="0x222",
        value=1.0,
        asset="ETH",
        timestamp=123,
    )
    tx3 = WalletTransaction(
        tx_hash="0xdef",
        from_address="0x333",
        to_address="0x444",
        value=2.0,
        asset="BTC",
        timestamp=456,
    )

    assert tx1 == tx2
    assert tx1 != tx3


def test_wallet_balance_repr():
    balance = WalletBalance(chain="ethereum", asset="ETH", amount=1.5)
    repr_str = repr(balance)

    assert "ethereum" in repr_str
    assert "ETH" in repr_str
    assert "1.5" in repr_str


def test_wallet_transaction_repr():
    tx = WalletTransaction(
        tx_hash="0xabc123",
        from_address="0x111",
        to_address="0x222",
        value=1.0,
        asset="ETH",
        timestamp=1234567890,
    )
    repr_str = repr(tx)

    assert "0xabc123" in repr_str
    assert "ETH" in repr_str
