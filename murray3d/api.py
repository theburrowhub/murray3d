from __future__ import annotations

import json as _json
from pathlib import Path

import httpx

from .config import Settings
from .models import Model3D, Pack, Profile


class ApiError(Exception):
    def __init__(self, status: int, detail: str):
        self.status = status
        self.detail = detail
        super().__init__(f"[{status}] {detail}")


class AuthError(ApiError):
    pass


class NotFoundError(ApiError):
    pass


class ValidationError(ApiError):
    pass


def _detail(resp: httpx.Response) -> str:
    try:
        data = resp.json()
    except ValueError:
        return resp.text or resp.reason_phrase
    if isinstance(data, dict) and "detail" in data:
        d = data["detail"]
        return d if isinstance(d, str) else _json.dumps(d, ensure_ascii=False)
    return _json.dumps(data, ensure_ascii=False)


class Client:
    def __init__(self, settings: Settings, transport: httpx.BaseTransport | None = None):
        self.settings = settings
        self._http = httpx.Client(
            base_url=settings.base_url,
            headers={"X-API-Key": settings.api_key},
            timeout=120.0,
            transport=transport,
        )

    def __enter__(self) -> "Client":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _raise_for_status(self, resp: httpx.Response) -> None:
        if resp.status_code >= 400:
            detail = _detail(resp)
            if resp.status_code == 401:
                raise AuthError(401, detail)
            if resp.status_code == 404:
                raise NotFoundError(404, detail)
            if resp.status_code == 422:
                raise ValidationError(422, detail)
            raise ApiError(resp.status_code, detail)

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        resp = self._http.request(method, path, **kwargs)
        self._raise_for_status(resp)
        return resp

    def whoami(self) -> Profile:
        resp = self._request("GET", "/auth/me")
        return Profile.model_validate(resp.json())

    def _params(self, **kw) -> dict:
        out = {}
        for k, v in kw.items():
            if v is None:
                continue
            out[k] = "true" if v is True else "false" if v is False else v
        return out

    def list_models(self, q=None, tag=None, category=None, only_published=None,
                    mine=False, limit=100, offset=0) -> list[Model3D]:
        params = self._params(q=q, tag=tag, category=category,
                              only_published=only_published, limit=limit, offset=offset)
        resp = self._request("GET", "/models", params=params)
        models = [Model3D.model_validate(x) for x in resp.json()]
        if mine:
            me = self.whoami()
            models = [m for m in models if m.owner_id == me.id]
        return models

    def get_model(self, model_id: int) -> Model3D:
        resp = self._request("GET", f"/models/{model_id}")
        return Model3D.model_validate(resp.json())

    def upload_model(self, file: Path, title: str, description="", category=None,
                     tags=None, price_eur=None, thumbnail=None) -> Model3D:
        file = Path(file)
        data = {"title": title, "description": description}
        if category is not None:
            data["category"] = category
        if tags:
            data["tags"] = ",".join(tags)
        if price_eur is not None:
            data["price_eur"] = str(price_eur)
        files = {"file": (file.name, file.read_bytes())}
        if thumbnail is not None:
            thumbnail = Path(thumbnail)
            files["thumbnail"] = (thumbnail.name, thumbnail.read_bytes())
        resp = self._request("POST", "/models", data=data, files=files)
        return Model3D.model_validate(resp.json())

    def update_model(self, model_id: int, **fields) -> Model3D:
        payload = {k: v for k, v in fields.items() if v is not None}
        resp = self._request("PATCH", f"/models/{model_id}", json=payload)
        return Model3D.model_validate(resp.json())

    def publish_model(self, model_id: int, **fields) -> Model3D:
        return self.update_model(model_id, published=True, **fields)

    def delete_model(self, model_id: int) -> None:
        self._request("DELETE", f"/models/{model_id}")

    def set_thumbnail(self, model_id: int, image: Path) -> Model3D:
        image = Path(image)
        files = {"thumbnail": (image.name, image.read_bytes())}
        resp = self._request("POST", f"/models/{model_id}/thumbnail", files=files)
        return Model3D.model_validate(resp.json())

    def download_model(self, model_id: int, dest: Path) -> Path:
        dest = Path(dest)
        with self._http.stream("GET", f"/models/{model_id}/download") as r:
            if r.status_code >= 400:
                r.read()
                self._raise_for_status(r)
            body = r.read()
        dest.write_bytes(body)
        return dest

    def list_packs(self, q=None, only_published=None, limit=100, offset=0) -> list[Pack]:
        resp = self._request("GET", "/packs", params=self._params(
            q=q, only_published=only_published, limit=limit, offset=offset))
        return [Pack.model_validate(x) for x in resp.json()]

    def get_pack(self, pack_id: int) -> Pack:
        resp = self._request("GET", f"/packs/{pack_id}")
        return Pack.model_validate(resp.json())

    def create_pack(self, title, description="", tags=None, price_eur=None,
                    cover=None, model_ids=None, published=False) -> Pack:
        payload = {
            "title": title,
            "description": description,
            "tags": tags or [],
            "model_ids": model_ids or [],
            "published": published,
        }
        if price_eur is not None:
            payload["price_eur"] = price_eur
        if cover is not None:
            payload["cover"] = cover
        resp = self._request("POST", "/packs", json=payload)
        return Pack.model_validate(resp.json())

    def update_pack(self, pack_id: int, **fields) -> Pack:
        payload = {k: v for k, v in fields.items() if v is not None}
        resp = self._request("PATCH", f"/packs/{pack_id}", json=payload)
        return Pack.model_validate(resp.json())

    def delete_pack(self, pack_id: int) -> None:
        self._request("DELETE", f"/packs/{pack_id}")

    def add_models_to_pack(self, pack_id: int, model_ids: list[int]) -> Pack:
        pack = self.get_pack(pack_id)
        merged = list(pack.model_ids)
        for mid in model_ids:
            if mid not in merged:
                merged.append(mid)
        return self.update_pack(pack_id, model_ids=merged)

    def get_config(self) -> dict:
        resp = self._request("GET", "/config")
        return resp.json()
