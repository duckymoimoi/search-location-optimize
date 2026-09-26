"""Minimal Elasticsearch HTTP client used by the demo API."""
from __future__ import annotations

import http.client
import json
from typing import Any
from urllib.parse import urlparse

class ElasticsearchClient:
    def __init__(self, base_url: str):
        parsed = urlparse(base_url)
        self.connection = http.client.HTTPConnection(parsed.hostname, parsed.port or 80, timeout=60)

    def request(self, method: str, path: str, body: Any | None = None) -> Any:
        payload = None if body is None else json.dumps(body).encode("utf-8")
        self.connection.request(method, path, body=payload, headers={"Content-Type": "application/json"})
        response = self.connection.getresponse()
        content = response.read()
        if response.status >= 400:
            raise RuntimeError(f"Elasticsearch {response.status}: {content.decode(errors='replace')}")
        return json.loads(content) if content else None
