import json
import os
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, quote, urlparse
from urllib.request import Request, urlopen


class InvoiceStorageError(RuntimeError):
    pass


class SupabaseInvoiceStorage:
    bucket = "travel-invoices"

    def __init__(self) -> None:
        self.url = os.environ.get("SUPABASE_URL", "").rstrip("/")
        self.service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")

    def _request(self, path: str, *, method: str, payload: dict | None = None) -> dict:
        if not self.url or not self.service_key:
            raise InvoiceStorageError("Invoice cloud storage is not configured yet.")
        body = json.dumps(payload).encode() if payload is not None else None
        request = Request(
            f"{self.url}{path}", data=body, method=method,
            headers={
                "apikey": self.service_key,
                "Authorization": f"Bearer {self.service_key}",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=15) as response:
                raw = response.read().decode()
                return json.loads(raw) if raw else {}
        except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
            raise InvoiceStorageError("Could not reach private invoice storage.") from exc

    def create_upload_token(self, storage_path: str) -> str:
        encoded_path = quote(storage_path, safe="/")
        data = self._request(
            f"/storage/v1/object/upload/sign/{self.bucket}/{encoded_path}",
            method="POST", payload={"upsert": True},
        )
        token = data.get("token")
        if not token and data.get("url"):
            token = parse_qs(urlparse(data["url"]).query).get("token", [None])[0]
        if not token:
            raise InvoiceStorageError("Could not prepare a secure invoice upload.")
        return token

    def signed_download_url(self, storage_path: str, filename: str) -> str:
        encoded_path = quote(storage_path, safe="/")
        data = self._request(
            f"/storage/v1/object/sign/{self.bucket}/{encoded_path}",
            method="POST", payload={"expiresIn": 300, "download": filename},
        )
        signed_url = data.get("signedURL") or data.get("signedUrl")
        if not signed_url:
            raise InvoiceStorageError("Could not prepare a secure invoice download.")
        return signed_url if signed_url.startswith("http") else f"{self.url}/storage/v1{signed_url}"

    def delete(self, storage_path: str) -> None:
        self._request(
            f"/storage/v1/object/{self.bucket}/{quote(storage_path, safe='/')}", method="DELETE"
        )
