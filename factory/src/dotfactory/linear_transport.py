"""HTTP transport for the Linear GraphQL client."""
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any, Callable, Mapping

Transport = Callable[[str, Mapping[str, str], bytes, float], dict[str, Any]]


class LinearAPIError(RuntimeError):
    def __init__(
        self, code: str, message: str, *, retryable: bool, ambiguous: bool = False,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.ambiguous = ambiguous
        self.headers = headers
        self.rate_limit = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code, "message": str(self),
            "retryable": self.retryable, "ambiguous": self.ambiguous,
        }


class GraphQLResponse(dict):
    def __init__(self, data, headers):
        super().__init__(data)
        self.headers = headers


def rate_headers(headers):
    if headers is None:
        return {}
    return {name.lower(): value for name, value in headers.items()
            if name.lower() in {"retry-after", "x-complexity"} or name.lower().startswith("x-ratelimit-")}


def default_transport(endpoint, headers, body, timeout):
    request = urllib.request.Request(endpoint, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            response_headers = rate_headers(response.headers)
    except urllib.error.HTTPError as error:
        raise LinearAPIError(
            f"http_{error.code}", "Linear GraphQL request failed",
            retryable=error.code == 429 or error.code >= 500,
            headers=rate_headers(error.headers) if error.code == 429 else None,
        ) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise LinearAPIError(
            "transport_error", "Linear GraphQL result is unknown",
            retryable=True, ambiguous=True,
        ) from error
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise LinearAPIError("invalid_response", "Linear returned invalid JSON", retryable=False) from error
    if not isinstance(decoded, dict):
        raise LinearAPIError("invalid_response", "Linear returned a non-object response", retryable=False)
    return GraphQLResponse(decoded, response_headers)
