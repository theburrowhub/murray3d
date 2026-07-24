# murray3d — Makefile
# Arranque de la app y tareas de desarrollo.
# La API key se lee de .env (MURRAY_API_KEY), que se genera desde key.txt y
# queda FUERA del control de versiones (.gitignore).

VENV := .venv
BIN  := $(VENV)/bin
PY   := $(BIN)/python
PIP  := $(BIN)/pip

.DEFAULT_GOAL := help
.PHONY: help setup env run gui cli whoami models packs test test-integration clean distclean

help: ## Muestra esta ayuda
	@echo "murray3d — objetivos disponibles:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'
	@echo ""
	@echo "Uso típico:  make setup   (una vez)   ->   make run"

$(BIN)/murray3d: ## (interno) instala el proyecto si falta
	@$(MAKE) setup

setup: ## Crea el venv e instala todo (deps + Chromium de Playwright + model-viewer)
	@test -d $(VENV) || python3 -m venv $(VENV)
	$(PIP) install -U pip
	$(PIP) install -e ".[dev]"
	$(PY) -m playwright install chromium
	$(PY) -m murray3d.gui.assets.download_model_viewer
	@echo "Setup completo. Ahora: make run"

env: ## Crea .env (desde key.txt si existe, o desde .env.dist) si no existe aún
	@if [ -f .env ]; then \
		echo ".env ya existe (no se sobreescribe)."; \
	elif [ -f key.txt ]; then \
		key=$$(head -n1 key.txt | tr -d '[:space:]'); \
		if [ -z "$$key" ]; then echo "key.txt está vacío"; exit 1; fi; \
		printf 'MURRAY_API_KEY=%s\n' "$$key" > .env; \
		echo ".env generado desde key.txt (git-ignored)."; \
	else \
		cp .env.dist .env; \
		echo ".env creado desde .env.dist — EDÍTALO y pon tu MURRAY_API_KEY."; \
	fi

guard-installed:
	@if [ ! -x $(BIN)/murray3d ]; then \
		echo "La app no está instalada. Ejecuta 'make setup' primero."; exit 1; \
	fi

run: env guard-installed ## Arranca la GUI de la app (carga .env)
	@set -a; . ./.env; set +a; $(BIN)/murray3d gui

gui: run ## Alias de 'run'

cli: env guard-installed ## Ejecuta el CLI: make cli ARGS="models list"
	@set -a; . ./.env; set +a; $(BIN)/murray3d $(ARGS)

whoami: env guard-installed ## Comprueba la autenticación (perfil)
	@set -a; . ./.env; set +a; $(BIN)/murray3d whoami

models: env guard-installed ## Lista tus modelos
	@set -a; . ./.env; set +a; $(BIN)/murray3d models list

packs: env guard-installed ## Lista los packs
	@set -a; . ./.env; set +a; $(BIN)/murray3d packs list

test: guard-installed ## Ejecuta los tests unitarios (rápidos)
	$(PY) -m pytest -q

test-integration: guard-installed ## Ejecuta el test de render real (requiere Chromium de Playwright)
	$(PY) -m pytest -q -m integration

clean: ## Borra cachés de Python y artefactos temporales
	find . -type d -name __pycache__ -prune -exec rm -rf {} + 2>/dev/null || true
	rm -rf .pytest_cache *.egg-info build dist

distclean: clean ## clean + borra el venv (no toca .env ni key.txt)
	rm -rf $(VENV)
