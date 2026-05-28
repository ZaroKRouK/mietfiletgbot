import aiohttp
import logging
from typing import Tuple, Optional

logger = logging.getLogger(__name__)


class FileServerClient:
    def __init__(self, base_url: str, username: str, password: str):
        self.base_url = base_url.rstrip('/')
        self.auth = aiohttp.BasicAuth(username, password)

    async def _request_json(self, method: str, endpoint: str, json_data: dict = None) -> dict:
        """Выполняет запрос с JSON‑данными (без файлов)"""
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.request(
                method=method,
                url=url,
                auth=self.auth,
                json=json_data
            ) as resp:
                text = await resp.text()
                logger.debug(f"{method} {url} -> {resp.status}, body: {text[:200]}")
                if resp.status >= 400:
                    raise Exception(f"HTTP {resp.status}: {text}")
                if resp.status == 204:
                    return {}
                return await resp.json()

    async def _request_file(self, method: str, endpoint: str, file_field: str,
                            filename: str, file_bytes: bytes, content_type: str = None) -> str:
        """Выполняет multipart-запрос с файлом, возвращает текст ответа (fid)"""
        url = f"{self.base_url}{endpoint}"
        form = aiohttp.FormData()
        form.add_field(
            file_field,
            file_bytes,
            filename=filename,
            content_type=content_type or 'application/octet-stream'
        )
        async with aiohttp.ClientSession() as session:
            async with session.request(method, url, auth=self.auth, data=form) as resp:
                text = await resp.text()
                logger.debug(f"{method} {url} -> {resp.status}, body: {text[:200]}")
                if resp.status >= 400:
                    raise Exception(f"HTTP {resp.status}: {text}")
                return text.strip()  # возвращаем строку (fid)

    # --- API methods ---

    async def create_user(self, username: str) -> Tuple[str, str]:
        """Создаёт обычного пользователя от имени CLIENT"""
        endpoint = f"/api/v1/client/users?username={username}"
        data = await self._request_json("POST", endpoint)
        return data["username"], data["password"]

    async def upload_file(self, file_bytes: bytes, filename: str) -> str:
        endpoint = "/api/v1/files/upload"
        fid = await self._request_file(
            method="POST",
            endpoint=endpoint,
            file_field="file",
            filename=filename,
            file_bytes=file_bytes
        )
        return fid

    async def download_file(self, fid: str) -> bytes:
        """Скачивает файл, возвращает содержимое в байтах"""
        endpoint = f"/api/v1/files/download/{fid}"
        url = f"{self.base_url}{endpoint}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url, auth=self.auth) as resp:
                if resp.status == 403:
                    raise Exception("Нет доступа к этому файлу")
                if resp.status != 200:
                    text = await resp.text()
                    raise Exception(f"HTTP {resp.status}: {text}")
                return await resp.read()