import hmac
import os

from fastapi import Header, HTTPException


def require_api_key(x_api_key: str = Header(default="")) -> None:
    expected = os.environ.get("API_KEY", "")
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


def require_benchmark_password(x_benchmark_password: str = Header(default="")) -> None:
    """Gate for the System Benchmark. Locked (403) until BENCHMARK_PASSWORD is set on the server."""
    expected = os.environ.get("BENCHMARK_PASSWORD", "")
    if not expected:
        raise HTTPException(status_code=403, detail="The benchmark is locked: BENCHMARK_PASSWORD is not set on the server.")
    if not hmac.compare_digest(x_benchmark_password.encode(), expected.encode()):
        raise HTTPException(status_code=401, detail="Incorrect password.")
