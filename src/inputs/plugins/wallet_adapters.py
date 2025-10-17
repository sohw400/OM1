import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional

from .wallet_base import WalletBalance, WalletTransaction


class ChainAdapter(ABC):
    """
    Abstract base class for blockchain-specific adapters.

    Each blockchain (Ethereum, Solana, Bitcoin, etc.) has its own
    adapter implementation that handles chain-specific logic.
    """

    def __init__(self, rpc_url: Optional[str] = None):
        """
        Initialize chain adapter.

        Parameters
        ----------
        rpc_url : Optional[str]
            RPC endpoint URL for this chain
        """
        self.rpc_url = rpc_url
        self.chain_id: str = ""

    @abstractmethod
    async def get_balance(self, address: str, asset: str = "native") -> Optional[WalletBalance]:
        """
        Get balance for an address.

        Parameters
        ----------
        address : str
            Wallet address
        asset : str
            Asset symbol (default: "native" for chain's native token)

        Returns
        -------
        Optional[WalletBalance]
            Balance information
        """
        pass

    @abstractmethod
    async def get_transactions(
        self, address: str, limit: int = 10
    ) -> List[WalletTransaction]:
        """
        Get recent transactions for an address.

        Parameters
        ----------
        address : str
            Wallet address
        limit : int
            Maximum number of transactions

        Returns
        -------
        List[WalletTransaction]
            Recent transactions
        """
        pass

    @abstractmethod
    def validate_address(self, address: str) -> bool:
        """
        Validate if address format is correct for this chain.

        Parameters
        ----------
        address : str
            Address to validate

        Returns
        -------
        bool
            True if valid address format
        """
        pass


class EthereumAdapter(ChainAdapter):
    """
    Adapter for Ethereum and EVM-compatible chains.

    Supports Ethereum mainnet, Polygon, BSC, Arbitrum, Optimism, and
    other EVM chains.
    """

    def __init__(self, rpc_url: Optional[str] = None, chain_name: str = "ethereum"):
        """
        Initialize Ethereum adapter.

        Parameters
        ----------
        rpc_url : Optional[str]
            RPC endpoint (defaults to public endpoint)
        chain_name : str
            Chain identifier (ethereum, polygon, bsc, etc.)
        """
        super().__init__(rpc_url)
        self.chain_id = chain_name

        # Default RPC URLs
        default_rpcs = {
            "ethereum": "https://eth.llamarpc.com",
            "polygon": "https://polygon-rpc.com",
            "bsc": "https://bsc-dataseed.binance.org",
            "arbitrum": "https://arb1.arbitrum.io/rpc",
            "optimism": "https://mainnet.optimism.io",
        }

        if not self.rpc_url:
            self.rpc_url = default_rpcs.get(chain_name, default_rpcs["ethereum"])

        try:
            from web3 import Web3

            self.web3 = Web3(Web3.HTTPProvider(self.rpc_url))
            if not self.web3.is_connected():
                logging.warning(f"Failed to connect to {chain_name} at {self.rpc_url}")
        except ImportError:
            logging.error("web3 library not installed")
            self.web3 = None

    async def get_balance(self, address: str, asset: str = "native") -> Optional[WalletBalance]:
        """
        Get ETH or ERC20 token balance.

        Parameters
        ----------
        address : str
            Ethereum address
        asset : str
            "native" for ETH or token symbol

        Returns
        -------
        Optional[WalletBalance]
            Balance information
        """
        if not self.web3:
            return None

        try:
            if asset == "native":
                balance_wei = self.web3.eth.get_balance(address)
                balance_eth = float(self.web3.from_wei(balance_wei, "ether"))

                asset_symbol = {
                    "ethereum": "ETH",
                    "polygon": "MATIC",
                    "bsc": "BNB",
                    "arbitrum": "ETH",
                    "optimism": "ETH",
                }.get(self.chain_id, "ETH")

                return WalletBalance(
                    chain=self.chain_id, asset=asset_symbol, amount=balance_eth
                )
        except Exception as e:
            logging.error(f"Error fetching {self.chain_id} balance: {e}")

        return None

    async def get_transactions(
        self, address: str, limit: int = 10
    ) -> List[WalletTransaction]:
        """
        Get recent transactions for an Ethereum address.

        Note: This is a basic implementation. Production would use
        block explorers (Etherscan API) for complete transaction history.

        Parameters
        ----------
        address : str
            Ethereum address
        limit : int
            Maximum transactions to return

        Returns
        -------
        List[WalletTransaction]
            Recent transactions
        """
        # Basic implementation - would need Etherscan API for full history
        return []

    def validate_address(self, address: str) -> bool:
        """
        Validate Ethereum address format.

        Parameters
        ----------
        address : str
            Address to validate

        Returns
        -------
        bool
            True if valid Ethereum address
        """
        if not self.web3:
            return False
        return self.web3.is_address(address)


class SolanaAdapter(ChainAdapter):
    """
    Adapter for Solana blockchain.

    Supports SOL and SPL tokens.
    """

    def __init__(self, rpc_url: Optional[str] = None):
        """
        Initialize Solana adapter.

        Parameters
        ----------
        rpc_url : Optional[str]
            Solana RPC endpoint (defaults to public endpoint)
        """
        super().__init__(rpc_url or "https://api.mainnet-beta.solana.com")
        self.chain_id = "solana"

        # Solana library would be imported here if available
        self.client = None

    async def get_balance(self, address: str, asset: str = "native") -> Optional[WalletBalance]:
        """
        Get SOL or SPL token balance.

        Parameters
        ----------
        address : str
            Solana address
        asset : str
            "native" for SOL or token mint address

        Returns
        -------
        Optional[WalletBalance]
            Balance information
        """
        # Solana implementation would go here
        # Requires solana-py or solders library
        logging.info(f"Solana balance check for {address} - implementation pending")
        return None

    async def get_transactions(
        self, address: str, limit: int = 10
    ) -> List[WalletTransaction]:
        """
        Get recent Solana transactions.

        Parameters
        ----------
        address : str
            Solana address
        limit : int
            Maximum transactions

        Returns
        -------
        List[WalletTransaction]
            Recent transactions
        """
        return []

    def validate_address(self, address: str) -> bool:
        """
        Validate Solana address format.

        Parameters
        ----------
        address : str
            Address to validate

        Returns
        -------
        bool
            True if valid Solana address (base58, 32-44 chars)
        """
        # Basic validation - Solana addresses are base58 encoded
        if not address or len(address) < 32 or len(address) > 44:
            return False
        # More thorough validation would use solana library
        return True


class AdapterFactory:
    """
    Factory for creating chain adapters.

    Simplifies adapter instantiation and management.
    """

    @staticmethod
    def create_adapter(chain: str, rpc_url: Optional[str] = None) -> Optional[ChainAdapter]:
        """
        Create appropriate adapter for the specified chain.

        Parameters
        ----------
        chain : str
            Chain identifier (ethereum, solana, polygon, etc.)
        rpc_url : Optional[str]
            Custom RPC URL

        Returns
        -------
        Optional[ChainAdapter]
            Chain adapter instance or None if unsupported
        """
        evm_chains = ["ethereum", "polygon", "bsc", "arbitrum", "optimism"]

        if chain in evm_chains:
            return EthereumAdapter(rpc_url=rpc_url, chain_name=chain)
        elif chain == "solana":
            return SolanaAdapter(rpc_url=rpc_url)
        else:
            logging.warning(f"Unsupported chain: {chain}")
            return None

    @staticmethod
    def get_supported_chains() -> List[str]:
        """
        Get list of all supported chains.

        Returns
        -------
        List[str]
            List of chain identifiers
        """
        return ["ethereum", "polygon", "bsc", "arbitrum", "optimism", "solana"]
