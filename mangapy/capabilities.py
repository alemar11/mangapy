from dataclasses import dataclass


@dataclass(frozen=True)
class ProviderCapabilities:
    max_parallel_chapters: int = 1
    max_parallel_pages: int = 1
    supports_batch_download: bool = False
    rate_limit: float | None = None  # requests per second, if enforced by caller
