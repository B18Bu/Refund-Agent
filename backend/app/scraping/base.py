from typing import Protocol
from app.commerce_schemas import ProductDTO


class BrandAdapter(Protocol):
    source_site: str
    source_url: str

    def parse(self, response_text: str, source_url: str) -> list[ProductDTO]: ...

