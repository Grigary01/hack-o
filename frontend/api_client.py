"""Frontend знает только HTTP-контракт. Никаких импортов storage или SQLite."""
import os
import httpx


class APIError(RuntimeError):
    def __init__(self, status_code, detail, code=None):
        self.status_code, self.detail, self.code = status_code, detail, code
        if isinstance(detail, list):
            message = '; '.join(('.'.join(str(part) for part in item.get('loc', []) if part != 'body')
                                + ': ' + item.get('msg', 'Неверные данные')) if isinstance(item, dict)
                                else str(item) for item in detail)
        else:
            message = str(detail)
        super().__init__(f'API {status_code}: {message}')


class APIClient:
    def __init__(self,base_url=None):
        self.base_url = (base_url or os.getenv('API_URL','http://127.0.0.1:8000')).rstrip('/')

    def request(self,method,path,payload=None):
        try:
            response = httpx.request(method,self.base_url+path,json=payload,timeout=150)
            if response.is_error:
                try:
                    error = response.json()
                    detail = error.get('detail',response.text) if isinstance(error,dict) else response.text[:300]
                    code = error.get('code') if isinstance(error,dict) else None
                except ValueError:
                    detail = response.text[:300]
                    code = None
                raise APIError(response.status_code, detail, code)
            return response.json()
        except httpx.HTTPError as exc:
            raise RuntimeError('Backend недоступен. Запустите uvicorn app.main:app на порту 8000.') from exc

    def get(self,path):
        return self.request('GET',path)

    def post(self,path,payload):
        return self.request('POST',path,payload)
