"""Cliente de la API REST de Freepik (generación text-to-image).

La API de Freepik es **asíncrona**: un POST crea una tarea y devuelve un
``task_id``; se consulta su estado por GET hasta ``COMPLETED`` (o ``FAILED``) y
entonces expone las URLs en ``generated``. Auth por header ``x-freepik-api-key``.

Notas de la API (verificadas contra docs.freepik.com):
- ``aspect_ratio`` NO acepta "3:4": usa el enum ``traditional_3_4`` (mapeado aquí).
- ``flux-dev`` NO admite ``negative_prompt`` (solo el endpoint clásico); se omite.
- Las URLs de ``generated`` son públicas (CDN), se descargan sin auth.

Se puede inyectar un ``transport`` de httpx y una función ``sleep`` para tests
(sin red ni esperas reales), igual que hace ``api.Client``.

Nota sobre 3D: Freepik NO expone generación 3D (glb/obj) por API; solo imagen y
upscaling. La malla 3D real requiere un paso posterior (image-to-3D de terceros,
p. ej. Tripo/Meshy) o el 3D Generator de la web app. Este cliente cubre la
generación de imágenes de referencia, que es la primera fase de autogeneración.
"""
from __future__ import annotations

import time
from pathlib import Path

import httpx

DEFAULT_BASE_URL = "https://api.freepik.com/v1"
DEFAULT_API_HEADER = "x-freepik-api-key"

# "3:4" (lo que trae el JSON) -> enum válido de la API de Freepik.
ASPECT_RATIO_MAP = {
    "1:1": "square_1_1",
    "4:3": "classic_4_3",
    "3:4": "traditional_3_4",
    "16:9": "widescreen_16_9",
    "9:16": "social_story_9_16",
    "3:2": "standard_3_2",
    "2:3": "portrait_2_3",
    "2:1": "horizontal_2_1",
    "1:2": "vertical_1_2",
    "4:5": "social_post_4_5",
}

# alias de modelo -> ruta base del endpoint. El polling es "<ruta>/{task_id}".
MODEL_ENDPOINTS = {
    "flux-dev": "/ai/text-to-image/flux-dev",
    "mystic": "/ai/mystic",
    "imagen3": "/ai/text-to-image/imagen3",
}
DEFAULT_MODEL = "flux-dev"


class FreepikError(Exception):
    pass


def map_aspect_ratio(value: str | None) -> str:
    """Traduce "3:4" al enum de Freepik; deja pasar un enum ya válido."""
    if not value:
        return ASPECT_RATIO_MAP["1:1"]
    if value in ASPECT_RATIO_MAP:
        return ASPECT_RATIO_MAP[value]
    return value  # se asume que ya es un enum válido (p. ej. "traditional_3_4")


def _endpoint(model: str | None) -> str:
    ep = MODEL_ENDPOINTS.get(model or DEFAULT_MODEL)
    if ep is None:
        raise FreepikError(
            f"Modelo no soportado: {model!r}. Usa uno de: "
            f"{', '.join(MODEL_ENDPOINTS)}."
        )
    return ep


class FreepikClient:
    """Cliente mínimo para generar imágenes a partir de prompts.

    ``generate(prompt, ...)`` crea la tarea y hace polling hasta obtener las URLs.
    ``download(url, dest)`` guarda una imagen a disco por streaming.
    """

    def __init__(self, api_key: str, base_url: str = DEFAULT_BASE_URL,
                 api_header: str = DEFAULT_API_HEADER,
                 transport: httpx.BaseTransport | None = None,
                 sleep=time.sleep, timeout: float = 60.0):
        if not api_key:
            raise FreepikError("Falta la API key de Freepik (FREEPIK_API_KEY).")
        self.base_url = base_url.rstrip("/")
        self._sleep = sleep
        self._http = httpx.Client(
            base_url=self.base_url,
            headers={api_header: api_key, "Content-Type": "application/json"},
            timeout=timeout,
            transport=transport,
        )

    def __enter__(self) -> "FreepikClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def _detail(self, resp: httpx.Response) -> str:
        try:
            data = resp.json()
        except ValueError:
            return resp.text or resp.reason_phrase
        if isinstance(data, dict):
            for k in ("message", "detail", "error"):
                if k in data:
                    return str(data[k])
        return str(data)

    def _request(self, method: str, path: str, *, max_retries: int = 5, **kwargs
                 ) -> httpx.Response:
        """Petición con reintento exponencial ante 429 (rate limit) y 5xx."""
        delay = 2.0
        for attempt in range(max_retries + 1):
            resp = self._http.request(method, path, **kwargs)
            if resp.status_code == 429 or resp.status_code >= 500:
                if attempt >= max_retries:
                    raise FreepikError(
                        f"[{resp.status_code}] {self._detail(resp)} "
                        f"(agotados {max_retries} reintentos)"
                    )
                retry_after = resp.headers.get("Retry-After")
                wait = float(retry_after) if retry_after and retry_after.isdigit() else delay
                self._sleep(wait)
                delay = min(delay * 2, 30.0)
                continue
            if resp.status_code >= 400:
                raise FreepikError(f"[{resp.status_code}] {self._detail(resp)}")
            return resp
        raise FreepikError("No se pudo completar la petición a Freepik.")

    def create_task(self, prompt: str, *, model: str = DEFAULT_MODEL,
                    aspect_ratio: str = "1:1", seed: int | None = None,
                    styling: dict | None = None,
                    negative_prompt: str | None = None) -> str:
        """Crea una tarea de generación y devuelve su ``task_id``."""
        if not prompt or not prompt.strip():
            raise FreepikError("El prompt está vacío.")
        endpoint = _endpoint(model)
        body: dict = {
            "prompt": prompt,
            "aspect_ratio": map_aspect_ratio(aspect_ratio),
        }
        if seed is not None:
            body["seed"] = int(seed)
        if styling:
            body["styling"] = styling
        # negative_prompt solo lo aceptan algunos endpoints (no flux-dev/mystic).
        if negative_prompt and model not in ("flux-dev", "mystic"):
            body["negative_prompt"] = negative_prompt
        resp = self._request("POST", endpoint, json=body)
        data = resp.json().get("data", {})
        task_id = data.get("task_id")
        if not task_id:
            raise FreepikError(f"Respuesta sin task_id: {resp.text}")
        return task_id

    def get_task(self, task_id: str, *, model: str = DEFAULT_MODEL
                 ) -> tuple[str, list[str]]:
        """Devuelve ``(status, urls)`` de una tarea. urls vacío si no ha terminado."""
        endpoint = f"{_endpoint(model)}/{task_id}"
        resp = self._request("GET", endpoint)
        data = resp.json().get("data", {})
        status = data.get("status", "UNKNOWN")
        urls = [u for u in (data.get("generated") or []) if u]
        return status, urls

    def generate(self, prompt: str, *, model: str = DEFAULT_MODEL,
                 aspect_ratio: str = "1:1", seed: int | None = None,
                 styling: dict | None = None, negative_prompt: str | None = None,
                 poll_interval: float = 3.0, timeout_s: float = 300.0) -> list[str]:
        """Crea la tarea, hace polling y devuelve las URLs generadas.

        Lanza ``FreepikError`` si la tarea falla o se agota ``timeout_s``.
        """
        task_id = self.create_task(
            prompt, model=model, aspect_ratio=aspect_ratio, seed=seed,
            styling=styling, negative_prompt=negative_prompt,
        )
        deadline = timeout_s
        waited = 0.0
        while True:
            status, urls = self.get_task(task_id, model=model)
            if status == "COMPLETED":
                if not urls:
                    raise FreepikError(f"Tarea {task_id} completada sin imágenes.")
                return urls
            if status == "FAILED":
                raise FreepikError(f"Tarea {task_id} falló (status FAILED).")
            if waited >= deadline:
                raise FreepikError(
                    f"Tarea {task_id} no terminó en {timeout_s:.0f}s (último: {status})."
                )
            self._sleep(poll_interval)
            waited += poll_interval

    def download(self, url: str, dest: Path) -> Path:
        """Descarga una URL de resultado a disco por streaming (sin auth)."""
        return download_url(url, dest)


def download_url(url: str, dest: Path) -> Path:
    """Descarga una URL pública a disco por streaming (sin auth).

    A nivel de módulo para reutilizarla desde el backend de agente sin construir
    un ``FreepikClient`` (que exigiría API key).
    """
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with httpx.stream("GET", url, timeout=120.0, follow_redirects=True) as r:
        if r.status_code >= 400:
            r.read()
            raise FreepikError(f"[{r.status_code}] al descargar {url}")
        with open(dest, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=1024 * 256):
                f.write(chunk)
    return dest
