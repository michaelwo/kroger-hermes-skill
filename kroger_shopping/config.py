import os
from dataclasses import dataclass
from typing import Optional, Union

from .models import ProductFulfillment


@dataclass
class KrogerConfig:
    """Configuration for the Kroger client."""
    client_id: str
    client_secret: str
    redirect_uri: str = "http://localhost:8080/callback"
    default_location_id: Optional[str] = "02100998"
    default_fulfillment: Optional[Union[ProductFulfillment, str]] = ProductFulfillment.CSP
    token_file: str = os.path.expanduser("~/.kroger_tokens.json")

    def __post_init__(self):
        if isinstance(self.default_fulfillment, str):
            try:
                self.default_fulfillment = ProductFulfillment(self.default_fulfillment)
            except ValueError as exc:
                allowed = ", ".join(item.value for item in ProductFulfillment)
                raise ValueError(f"KROGER_DEFAULT_FULFILLMENT must be one of: {allowed}") from exc

    @classmethod
    def from_env(cls) -> "KrogerConfig":
        """Load configuration from environment variables."""
        client_id = os.getenv("KROGER_CLIENT_ID")
        client_secret = os.getenv("KROGER_CLIENT_SECRET")

        if not client_id or not client_secret:
            raise ValueError(
                "KROGER_CLIENT_ID and KROGER_CLIENT_SECRET must be set"
            )

        return cls(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=os.getenv(
                "KROGER_REDIRECT_URI", "http://localhost:8080/callback"
            ),
            default_location_id=os.getenv("KROGER_DEFAULT_LOCATION_ID", "02100998"),
            default_fulfillment=os.getenv(
                "KROGER_DEFAULT_FULFILLMENT",
                ProductFulfillment.CSP.value,
            ),
            token_file=os.getenv(
                "KROGER_TOKEN_FILE",
                os.path.expanduser("~/.kroger_tokens.json")
            ),
        )