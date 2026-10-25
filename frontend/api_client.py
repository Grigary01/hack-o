"""Frontend знает только HTTP-контракт. Никаких импортов storage или SQLite."""
import os
import httpx


class APIClient:
    def __init__(self,base_url=None):
        self.base_url = (base_url or os.getenv('API_URL','http://127.0.0.1:8000')).rstrip('/')

    def request(self,method,path,payload=None):
        try:
            response = httpx.request(method,self.base_url+path,json=payload,timeout=150)
            if response.is_error:
                try:
                    detail = response.json().get('detail',response.text)
                except ValueError:
                    detail = response.text[:300]
                raise RuntimeError(f'API {response.status_code}: {detail}')
            return response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError('Backend недоступен. Запустите uvicorn app.main:app на порту 8000.') from exc

    def get(self,path):
        return self.request('GET',path)

    def post(self,path,payload):
        return self.request('POST',path,payload)
