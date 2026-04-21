# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with
code in this repository.

> **Template baseline.** Extend this file with project-specific sections
> (project overview, commands, architecture, key files, etc.) — do not
> replace it. The Tool Execution, Git Hooks, and Git Workflow sections
> below encode engineering standards that should remain consistent across
> repositories.

## Tool Execution

Python is managed by [uv](https://docs.astral.sh/uv/). Run scripts with
`uv run python path/to/script.py` or inside an activated venv
(`source .venv/bin/activate`). The interpreter version is pinned in
`.python-version`; dependencies and metadata live in `pyproject.toml`.
Run `uv sync` after a fresh clone to create `.venv/`.

## Git Hooks (pre-commit)

Git hooks are managed by the [pre-commit](https://pre-commit.com/)
framework. Configuration lives in `.pre-commit-config.yaml`; per-hook
configs live in `commitlint.config.js` and `.gitleaks.toml`.

Install pre-commit once per machine (`pipx install pre-commit`), then
register the hooks per clone. `default_install_hook_types` in
`.pre-commit-config.yaml` already lists `pre-commit`, `commit-msg`, and
`pre-push`, so a single `install` registers all three:

```bash
pre-commit install --install-hooks
pre-commit autoupdate
```

**Hooks enforced:**

| Stage | Hook | Source | What it blocks |
| ----- | ---- | ------ | -------------- |
| pre-commit | baseline hygiene | pre-commit/pre-commit-hooks v6.0.0 | trailing whitespace, missing EOF newline, CRLF, merge conflicts, case conflicts, bad shebangs, files >10 MB, invalid YAML/JSON/TOML, private keys in tree |
| pre-commit | no-commit-to-branch | pre-commit/pre-commit-hooks v6.0.0 | Direct commits to `main`, `master`, `develop`, or any `release/*` branch |
| pre-commit | gitleaks | gitleaks/gitleaks v8.30.0 | ~200 provider-specific secret formats (AWS, GitHub PATs, Stripe, GCP, private-key blobs, high-entropy strings). Allowlist in `.gitleaks.toml` |
| pre-commit | shellcheck | shellcheck-py v0.11.0.1 | Shell scripting issues (severity ≥ warning) |
| commit-msg | commitlint | alessandrojcm/commitlint-pre-commit-hook v9.24.0 + `@commitlint/cli@19.5.0` | Non-conventional format, bad type, uppercase type, empty subject, trailing period, subject >72 chars |

Pins are maintained by `pre-commit autoupdate` — run periodically to pull
newer hook revisions. Merge and revert commits are auto-ignored by
commitlint so they pass the commit-msg hook.

**Manual hook execution:**

```bash
pre-commit run --all-files            # all hooks across the whole tree
pre-commit run gitleaks --all-files   # just one hook
```

## Git Workflow & Best Practices

When committing changes or managing git for this repository, adhere to the following:

1. **Feature Branches:** Always create a feature branch before making changes.
   Direct commits to `main` (and `master`, `develop`, `release/*`) are blocked
   locally by the `no-commit-to-branch` pre-commit hook; direct pushes to
   `main` are also blocked server-side by the `protect-main` repository
   ruleset (see "Server-side branch protection" below).
2. **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `docs:`,
   `chore:`, `refactor:`, `test:`, `ci:`, `style:`, `perf:`, `build:`, `revert:`.
   Include scopes where applicable (e.g., `feat(auth):`, `fix(api):`). Enforced
   by the commitlint commit-msg hook.
3. **Secret Safety:** NEVER commit plaintext credentials. Enforced by the
   gitleaks pre-commit hook. Keep secrets in `.env*` (gitignored) or an
   encrypted store; use templated placeholder files for anything that must be
   checked in.
4. **Atomic Commits:** Keep commits logically separated. Don't bundle unrelated
   changes (e.g., feature work, doc sweeps, and formatting refactors should be
   three commits).
5. **Pre-Commit Checks:** Automated via `pre-commit`. Manual run:
   `pre-commit run --all-files`.
6. **Clean History:** Prefer `git pull --rebase` when resolving divergent
   branches to keep a linear history.

### Server-side branch protection

`main` is protected on GitHub by the repository ruleset **`protect-main`**
(ID `15373845`). Enforcement is `active` and cannot be bypassed.

| Rule | Blocks |
| ---- | ------ |
| `deletion` | `git push origin --delete main` |
| `non_fast_forward` | Force-push to `main` (`--force`, `--force-with-lease`) |
| `pull_request` | Direct pushes to `main`; merges require a PR. `required_approving_review_count: 0` (solo-dev friendly); `required_review_thread_resolution: true` so any open conversation must be resolved before merge. |

Inspect or edit at <https://github.com/securexai/quanto/rules/15373845>.
To modify via CLI:

```bash
gh api repos/securexai/quanto/rulesets/15373845
gh api --method PUT repos/securexai/quanto/rulesets/15373845 --input <file>
```

### Commit signing (known deviation)

The global engineering standard requires signed commits (`git commit -S`).
This repo does **not** currently enforce signatures: no signing key is
configured, and the `protect-main` ruleset omits `required_signatures`.
When a signing key is set up (SSH signing via `gpg.format = ssh` is the
least-friction option on this host), revisit this section and add
`{"type": "required_signatures"}` to the ruleset.

---

## Project: Quanto

Quanto es un sistema de análisis financiero personal que procesa extractos
mensuales de Davivienda (cuenta + TC), Davibank (TC), y Nequi. Extrae
movimientos de PDFs oficiales, los categoriza, detecta transferencias
internas entre productos, y genera un dashboard HTML editorial.

### Entorno de trabajo

- **Host:** Fedora 43 Kinoite (Bazzite) — atómico/inmutable; `dnf install`
  directo en el host no está disponible.
- **Contenedor de dev:** toolbox `quanto` contiene el tooling mutable
  (pre-commit, pipx, gh, poppler-utils, nodejs, pnpm, markdownlint-cli2,
  dnf). Entrar con `toolbox enter quanto`; el `$HOME` se comparte con el
  host.
- **Hooks de git:** `pre-commit` sólo resuelve dentro del toolbox.
  Correr `git commit` y `git push` desde `toolbox enter quanto`; desde
  el host los hooks fallan con `pre-commit: command not found` y no se
  aplican (gitleaks, commitlint, no-commit-to-branch, shellcheck y los
  baseline checks quedan sin enforzar). Las herramientas subyacentes
  (gitleaks, commitlint, shellcheck) se instalan automáticamente por
  `pre-commit` en entornos aislados — no requieren instalación global.
- **Python:** 3.14 gestionado por uv (pinned en `.python-version`).
- **Shell:** Bash.

### Bootstrap del toolbox

Secuencia completa de setup en un toolbox `quanto` nuevo:

```bash
toolbox create --container quanto
toolbox enter quanto

# Herramientas base del sistema
sudo dnf install -y poppler-utils nodejs pipx

# pnpm standalone installer
curl -fsSL https://get.pnpm.io/install.sh | sh -
source ~/.bashrc   # o abrir nuevo shell

# Herramientas globales vía pnpm / pipx
pnpm add -g markdownlint-cli2   # lint manual de docs
pipx install pre-commit         # orquestador de git hooks

# GitHub CLI (si no viene en la imagen base)
sudo dnf install -y gh

# Setup del proyecto (una vez por clon)
cd ~/repos/quanto
uv sync
pre-commit install --install-hooks   # registra pre-commit + commit-msg + pre-push
pre-commit autoupdate

# Verificación
pdftotext -v
markdownlint-cli2 --version
pre-commit --version
gh --version
uv --version
```

Si algún comando falla con `command not found` después del setup,
revisar que el toolbox tenga en PATH los directorios de pnpm
(`~/.local/share/pnpm`) y pipx (`~/.local/bin`).

### Arquitectura

El sistema es un pipeline modular en 4 fases que escribe JSONs intermedios:

1. **Parsing** — 4 parsers (uno por banco/producto) leen PDFs vía
   `pdftotext -layout` (subprocess) y emiten JSON normalizado con
   movimientos, saldos y metadata del periodo.
2. **Cross-matching** — detecta pagos TC desde cuenta, fondeos Nequi desde
   Davivienda (BRE-B), y actualiza los JSONs marcando transferencias
   internas para que no se cuenten como gasto.
3. **Categorización** — aplica `.claude/skills/quanto-extractos/categorias.json`
   (~50 reglas keyword-based) a cada movimiento. Consolida gastos por
   categoría/subcategoría y produce `gastos-por-categoria.json`.
4. **Consolidación + análisis** — calcula métricas de patrimonio, rotación
   de deuda TC, intereses pagados. El análisis trimestral detecta
   suscripciones recurrentes y anomalías estadísticas.

### Estructura

```text
quanto/
├── .claude/
│   ├── agents/quanto.md                  ← sub-agente Claude Code
│   └── skills/quanto-extractos/
│       ├── categorias.json               ← diccionario de categorización
│       └── scripts/                      ← pipeline en 9 scripts
├── extractos/YYYY-MM/*.pdf              ← entrada (gitignored)
├── analisis/YYYY-MM/*.json              ← salida procesada (gitignored)
└── dashboard.html                       ← reporte visual (gitignored)
```

### Dependencias de sistema

- `pdftotext` (poppler-utils) — binario externo invocado por todos los
  parsers vía subprocess. En el host Kinoite/Bazzite viene en la imagen
  base (dependencia transitiva del escritorio KDE/Okular/Dolphin); en el
  toolbox `quanto` (imagen `fedora-toolbox` sin escritorio) hay que
  instalarlo explícitamente: `toolbox run -c quanto sudo dnf install poppler-utils`.
- No hay dependencias pip — todo el código usa stdlib.

### Comandos comunes

```bash
# Procesar un mes completo (el sub-agente automatiza esto)
MES="2026-04"
uv run python .claude/skills/quanto-extractos/scripts/parser_davivienda_ahorros.py \
  --pdf "extractos/$MES/davivienda-ahorros.pdf" \
  --output "analisis/$MES/davivienda-ahorros.json" --verbose

# (repetir para los otros 3 parsers...)

# Matcher cross-extracto
uv run python .claude/skills/quanto-extractos/scripts/matcher_cross_extracto.py \
  --ahorros "analisis/$MES/davivienda-ahorros.json" \
  --tc-davivienda "analisis/$MES/davivienda-tc.json" \
  --tc-davibank "analisis/$MES/davibank-tc.json" \
  --nequi "analisis/$MES/nequi.json" \
  --output "analisis/$MES/cross-match.json"

# Categorizar + consolidar
uv run python .claude/skills/quanto-extractos/scripts/categorizar_movimientos.py --mes $MES
uv run python .claude/skills/quanto-extractos/scripts/consolidar_mes.py --mes $MES

# Análisis trimestral + dashboard
uv run python .claude/skills/quanto-extractos/scripts/analizar_periodo.py \
  --meses 2026-01,2026-02,2026-03 \
  --output analisis/trimestre/analisis-trimestral.json
uv run python .claude/skills/quanto-extractos/scripts/generar_dashboard.py \
  --meses 2026-01,2026-02,2026-03 \
  --output dashboard.html
```

### Delegación al sub-agente Quanto

En Claude Code, el sub-agente `.claude/agents/quanto.md` automatiza los
workflows comunes. Se invoca automáticamente por el `description` match
cuando menciones extractos, gastos, o nombres de bancos. Delegación
explícita: `> use the quanto subagent`.

### Invariantes críticas

- **Nunca commitear PDFs ni JSONs de análisis** — contienen datos
  financieros personales. Protegido por `.gitignore`.
- **El parser de ahorros debe correrse ANTES del matcher** — el matcher
  modifica el JSON de ahorros in-place marcando fondeos a Nequi.
  Re-correr el matcher sin re-parsear ahorros duplica las marcas.
- **Keywords de categorización mínimo 4 caracteres** y completas
  ("TIENDAS ARA" no "ARA "). Bug histórico: "ARA " matcheaba "PARA DIANA"
  en Nequi y clasificaba mal decenas de movimientos.
- **Orden de reglas en `categorias.json` importa** — específicas antes
  que genéricas. La regla `transferencia_personal` con keyword "PARA "
  debe ir AL FINAL.
- **Validación de balance es obligatoria** — si un parser reporta
  validación OK pero la cifra no cuadra, probablemente el regex perdió
  una línea o un formato nuevo. Investigar antes de continuar.

  ---

## Testing approach

Este proyecto aplica TDD según la skill `tdd`, con contornos específicos
al dominio:

**System boundaries** (donde los mocks son aceptables según `mocking.md`):

- `pdftotext` subprocess calls — pero preferir golden files sobre mocks.
- File system writes a `analisis/` — testeable por inspección del output.
**No son boundaries** (nunca mockear):

- Módulos internos Python dentro del pipeline.
- La lógica de carga de `categorias.json`.
- Serialización/deserialización JSON.
**Estilo de test preferido para este codebase:**

- Golden file regression tests sobre unit tests para los parsers.
- End-to-end pipeline tests usando JSONs redacted en `tests/fixtures/`
  (los PDFs originales nunca se commitean; los fixtures son salidas
  anonimizadas de los parsers, no entradas).
- Invariant assertions embebidas en scripts (validación de balance,
  count checks) como primera línea de defensa.
**Estado actual:** el repositorio aún no tiene test suite formal. Los
invariantes viven embebidos en los scripts del pipeline. Cuando aparezca
el primer módulo que amerite tests (por ejemplo, cálculos financieros
puros), introducir pytest y `tests/` siguiendo las convenciones de arriba.

**Cuándo iniciar el test suite de Quanto:** al introducir módulos de
lógica pura (cálculos financieros, simuladores, forecasting). Para esos
aplicar TDD según la skill. Mantener los scripts del pipeline sin tests
hasta que el enfoque de golden files demuestre ser insuficiente.

**Behaviors que vale la pena testear** (per skill's "You can't test
everything" principle):

- Correctness del cross-extract matching (Davivienda → Nequi fondeos).
- Que las reglas de categorización no produzcan falsos positivos
  (regression test para la clase de bug "ARA " → "PARA DIANA").
- Que los parsers rechacen input malformado claramente en vez de
  silenciosamente contar mal.
**Behaviors que NO vale la pena testear** (per el mismo principio):

- Patrones regex específicos en aislamiento.
- Cada keyword individual en `categorias.json`.
- Formato del JSON de salida.
Al implementar tests, seguir el ciclo red-green-refactor según la skill
`tdd`.
