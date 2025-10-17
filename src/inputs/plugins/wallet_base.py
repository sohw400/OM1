from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional

from inputs.base import SensorConfig
from inputs.base.loop import FuserInput


@dataclass
class WalletBalance:
    """
    Represents a wallet balance for a specific asset.

    Parameters
    ----------
    chain : str
        Blockchain identifier (e.g., "ethereum", "solana", "bitcoin")
    asset : str
        Asset symbol (e.g., "ETH", "SOL", "BTC")
    amount : float
        Balance amount
    usd_value : Optional[float]
        USD value of the balance if available
    """

    chain: str
    asset: str
    amount: float
    usd_value: Optional[float] = None


@dataclass
class WalletTransaction:
    """
    Represents a detected wallet transaction.

    Parameters
    ----------
    chain : str
        Blockchain where transaction occurred
    tx_hash : str
        Transaction hash
    asset : str
        Asset transferred
    amount : float
        Amount transferred
    from_address : str
        Sender address
    to_address : str
        Receiver address
    timestamp : float
        Unix timestamp of transaction
    """

    chain: str
    tx_hash: str
    asset: str
    amount: float
    from_address: str
    to_address: str
    timestamp: float


class WalletBase(FuserInput[Dict], ABC):
    """
    Abstract base class for all wallet providers.

    This class defines the standard interface that all wallet implementations
    must follow, enabling OM1 to support multiple wallet types through a
    unified API.

    Subclasses must implement methods for connecting wallets, retrieving
    balances, and monitoring transactions across different blockchain networks.
    """

    def __init__(self, config: SensorConfig = SensorConfig()):
        """
        Initialize the wallet provider.

        Parameters
        ----------
        config : SensorConfig
            Configuration for the wallet provider
        """
        super().__init__(config)
        self.config = config
        self.connected = False
        self.wallet_address: Optional[str] = None

    @abstractmethod
    async def connect(self) -> bool:
        """
        Connect to the wallet provider.

        Returns
        -------
        bool
            True if connection successful, False otherwise
        """
        pass

    @abstractmethod
    async def disconnect(self):
        """
        Disconnect from the wallet provider and clean up resources.
        """
        pass

    @abstractmethod
    async def get_balance(self, chain: str, asset: str) -> Optional[WalletBalance]:
        """
        Get balance for a specific asset on a specific chain.

        Parameters
        ----------
        chain : str
            Blockchain identifier (e.g., "ethereum", "solana")
        asset : str
            Asset symbol (e.g., "ETH", "SOL")

        Returns
        -------
        Optional[WalletBalance]
            Balance information or None if unavailable
        """
        pass

    @abstractmethod
    async def get_all_balances(self) -> List[WalletBalance]:
        """
        Get all balances across all supported chains.

        Returns
        -------
        List[WalletBalance]
            List of all non-zero balances
        """
        pass

    @abstractmethod
    async def get_recent_transactions(
        self, chain: str, limit: int = 10
    ) -> List[WalletTransaction]:
        """
        Get recent transactions for a specific chain.

        Parameters
        ----------
        chain : str
            Blockchain identifier
        limit : int
            Maximum number of transactions to return

        Returns
        -------
        List[WalletTransaction]
            List of recent transactions
        """
        pass

    def get_supported_chains(self) -> List[str]:
        """
        Get list of supported blockchain networks.

        Returns
        -------
        List[str]
            List of supported chain identifiers
        """
        return []

    def get_supported_wallets(self) -> List[str]:
        """
        Get list of supported wallet types.

        Returns
        -------
        List[str]
            List of supported wallet names
        """
        return []
