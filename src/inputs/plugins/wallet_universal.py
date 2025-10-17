import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Dict, List, Optional

from inputs.base import SensorConfig
from providers.io_provider import IOProvider

from .wallet_adapters import AdapterFactory, ChainAdapter
from .wallet_base import WalletBalance, WalletBase, WalletTransaction


@dataclass
class Message:
    """
    Container for timestamped wallet messages.

    Parameters
    ----------
    timestamp : float
        Unix timestamp
    message : str
        Message content
    """

    timestamp: float
    message: str


class WalletUniversal(WalletBase):
    """
    Universal wallet connector supporting 300+ wallets.

    This implementation uses chain adapters to support multiple blockchains
    and wallet types through a unified interface. It works with any wallet
    that supports standard blockchain RPCs.

    Supported wallets include (but not limited to):
    - Ethereum: MetaMask, Trust Wallet, Rainbow, Argent, Safe, Ledger
    - Solana: Phantom, Solflare, Backpack, Ledger
    - Multi-chain: WalletConnect (300+ wallets)

    Supported chains:
    - Ethereum (ETH)
    - Polygon (MATIC)
    - Binance Smart Chain (BNB)
    - Arbitrum (ETH)
    - Optimism (ETH)
    - Solana (SOL)
    """

    SUPPORTED_CHAINS = ["ethereum", "polygon", "bsc", "arbitrum", "optimism", "solana"]

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize universal wallet connector.

        Configuration options:
        - chains: List of chains to monitor (default: ["ethereum"])
        - wallet_address: Wallet address to monitor
        - poll_interval: Seconds between balance checks (default: 10)
        - mock_mode: Use simulated data (default: False)
        """
        super().__init__(config)

        self.io_provider = IOProvider()
        self.messages: List[Message] = []

        # Configuration
        self.wallet_address = getattr(config, "wallet_address", None)
        self.poll_interval = getattr(config, "poll_interval", 10)
        self.mock_mode = getattr(config, "mock_mode", False)
        self.enabled_chains = getattr(config, "chains", ["ethereum"])

        # Initialize chain adapters
        self.adapters: Dict[str, ChainAdapter] = {}
        for chain in self.enabled_chains:
            adapter = AdapterFactory.create_adapter(chain)
            if adapter:
                self.adapters[chain] = adapter
                logging.info(f"Initialized adapter for {chain}")

        # Balance tracking
        self.balances: Dict[str, WalletBalance] = {}
        self.previous_balances: Dict[str, float] = {}

        if self.mock_mode:
            logging.info("WalletUniversal running in mock mode")
            self.wallet_address = "0xMOCK_ADDRESS"
        elif not self.wallet_address:
            logging.warning("No wallet address configured")

        self.descriptor_for_LLM = "Wallet"

    async def connect(self) -> bool:
        """
        Connect to wallet (validate address and test adapters).

        Returns
        -------
        bool
            True if successfully connected
        """
        if self.mock_mode:
            self.connected = True
            return True

        if not self.wallet_address:
            logging.error("Cannot connect: No wallet address provided")
            return False

        # Validate address format for each chain
        for chain, adapter in self.adapters.items():
            if not adapter.validate_address(self.wallet_address):
                logging.warning(
                    f"Address {self.wallet_address} may not be valid for {chain}"
                )

        self.connected = True
        return True

    async def disconnect(self):
        """
        Disconnect and cleanup resources.
        """
        self.connected = False
        self.adapters.clear()

    async def get_balance(
        self, chain: str, asset: str = "native"
    ) -> Optional[WalletBalance]:
        """
        Get balance for specific chain and asset.

        Parameters
        ----------
        chain : str
            Chain identifier
        asset : str
            Asset symbol

        Returns
        -------
        Optional[WalletBalance]
            Balance information
        """
        if self.mock_mode:
            return self._get_mock_balance(chain, asset)

        adapter = self.adapters.get(chain)
        if not adapter or not self.wallet_address:
            return None

        return await adapter.get_balance(self.wallet_address, asset)

    async def get_all_balances(self) -> List[WalletBalance]:
        """
        Get all balances across all enabled chains.

        Returns
        -------
        List[WalletBalance]
            List of all balances
        """
        balances = []
        for chain in self.enabled_chains:
            balance = await self.get_balance(chain, "native")
            if balance and balance.amount > 0:
                balances.append(balance)
        return balances

    async def get_recent_transactions(
        self, chain: str, limit: int = 10
    ) -> List[WalletTransaction]:
        """
        Get recent transactions for a chain.

        Parameters
        ----------
        chain : str
            Chain identifier
        limit : int
            Maximum transactions to return

        Returns
        -------
        List[WalletTransaction]
            Recent transactions
        """
        if self.mock_mode:
            return []

        adapter = self.adapters.get(chain)
        if not adapter or not self.wallet_address:
            return []

        return await adapter.get_transactions(self.wallet_address, limit)

    def _get_mock_balance(self, chain: str, asset: str) -> WalletBalance:
        """
        Generate mock balance data for testing.

        Parameters
        ----------
        chain : str
            Chain identifier
        asset : str
            Asset symbol

        Returns
        -------
        WalletBalance
            Simulated balance
        """
        import random

        base_amounts = {
            "ethereum": 1.5,
            "polygon": 500.0,
            "bsc": 0.5,
            "solana": 10.0,
            "arbitrum": 0.8,
            "optimism": 0.6,
        }

        asset_symbols = {
            "ethereum": "ETH",
            "polygon": "MATIC",
            "bsc": "BNB",
            "solana": "SOL",
            "arbitrum": "ETH",
            "optimism": "ETH",
        }

        base_amount = base_amounts.get(chain, 1.0)
        variation = random.uniform(-0.1, 0.1)
        amount = base_amount + variation

        return WalletBalance(
            chain=chain, asset=asset_symbols.get(chain, "TOKEN"), amount=amount
        )

    async def _poll(self) -> Dict[str, List[WalletBalance]]:
        """
        Poll for balance updates across all chains.

        Returns
        -------
        Dict[str, List[WalletBalance]]
            Dictionary mapping chain to list of balances with changes
        """
        await asyncio.sleep(self.poll_interval)

        changes = {}
        for chain in self.enabled_chains:
            balance = await self.get_balance(chain, "native")
            if balance:
                key = f"{chain}_{balance.asset}"
                previous = self.previous_balances.get(key, balance.amount)

                if balance.amount != previous:
                    changes[chain] = [balance]
                    self.previous_balances[key] = balance.amount

        return changes

    async def _raw_to_text(
        self, raw_input: Dict[str, List[WalletBalance]]
    ) -> Optional[Message]:
        """
        Convert balance changes to human-readable text.

        Parameters
        ----------
        raw_input : Dict[str, List[WalletBalance]]
            Balance changes by chain

        Returns
        -------
        Optional[Message]
            Formatted message
        """
        if not raw_input:
            return None

        messages = []
        for chain, balances in raw_input.items():
            for balance in balances:
                if balance.amount > 0:
                    messages.append(
                        f"Your {chain.capitalize()} wallet balance is now "
                        f"{balance.amount:.4f} {balance.asset}."
                    )

        if not messages:
            return None

        combined_message = " ".join(messages)
        return Message(timestamp=time.time(), message=combined_message)

    async def raw_to_text(self, raw_input: Dict[str, List[WalletBalance]]):
        """
        Process balance updates and manage message buffer.

        Parameters
        ----------
        raw_input : Dict[str, List[WalletBalance]]
            Raw balance data
        """
        pending_message = await self._raw_to_text(raw_input)

        if pending_message is not None:
            self.messages.append(pending_message)

    def formatted_latest_buffer(self) -> Optional[str]:
        """
        Format and clear the latest buffer contents.

        Returns
        -------
        Optional[str]
            Formatted string or None if buffer is empty
        """
        if len(self.messages) == 0:
            return None

        latest_message = self.messages[-1]

        result = f"""
INPUT: {self.descriptor_for_LLM}
// START
{latest_message.message}
// END
"""

        self.io_provider.add_input(
            self.__class__.__name__, latest_message.message, latest_message.timestamp
        )
        self.messages = []

        return result

    def get_supported_chains(self) -> List[str]:
        """
        Get list of supported chains.

        Returns
        -------
        List[str]
            Supported chain identifiers
        """
        return self.SUPPORTED_CHAINS

    def get_supported_wallets(self) -> List[str]:
        """
        Get list of supported wallet types.

        Returns
        -------
        List[str]
            List of wallet names
        """
        return [
            "MetaMask",
            "Trust Wallet",
            "Phantom",
            "Ledger",
            "Coinbase Wallet",
            "Rainbow",
            "Argent",
            "Safe",
            "WalletConnect (300+ wallets)",
            "Any wallet with blockchain RPC support",
        ]
