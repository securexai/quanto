# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

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

`lefthook` is a globally-installed tool and is invoked directly (no wrapper).

## Git Hooks (Lefthook)

Git hooks are managed by [Lefthook](https://github.com/evilmartians/lefthook).
Install it once globally — via `go install github.com/evilmartians/lefthook@latest`,
`npm install -g lefthook`, or a prebuilt binary from the
[releases page](https://github.com/evilmartians/lefthook/releases) — and run
`lefthook install` from the repo root to register hooks. Configuration lives
in `lefthook.yml`.

**Hooks enforced:**

| Hook | Check | What it blocks |
|------|-------|----------------|
| pre-commit | no-secrets | Plaintext password/token/secret patterns |
| pre-commit | branch-check | Direct commits to `main` |
| commit-msg | conventional-commit | Non-conventional commit message format |
| pre-push | branch-check | Direct pushes to `main` |

Add project-specific pre-push checks (test suites, integration tests, build
verification) by editing `lefthook.yml`. A commented placeholder is included.

**Manual hook execution:**

```bash
lefthook run pre-commit    # Run pre-commit hooks
lefthook run pre-push      # Run pre-push hooks
```

## Git Workflow & Best Practices

When committing changes or managing git for this repository, adhere to the following:

1. **Feature Branches:** Always create a feature branch before making changes.
   Direct commits and pushes to `main` are blocked by Lefthook hooks.
2. **Conventional Commits:** Use standard prefixes: `feat:`, `fix:`, `docs:`,
   `chore:`, `refactor:`, `test:`, `ci:`, `style:`, `perf:`, `build:`, `revert:`.
   Include scopes where applicable (e.g., `feat(auth):`, `fix(api):`). Enforced
   by the commit-msg hook.
3. **Secret Safety:** NEVER commit plaintext credentials. Enforced by the
   pre-commit `no-secrets` hook. Keep secrets in `.env*` (gitignored) or an
   encrypted store; use templated placeholder files for anything that must be
   checked in.
4. **Atomic Commits:** Keep commits logically separated. Don't bundle unrelated
   changes (e.g., feature work, doc sweeps, and formatting refactors should be
   three commits).
5. **Pre-Commit Checks:** Automated via Lefthook (no-secrets, branch-check).
   Manual: `lefthook run pre-commit`.
6. **Clean History:** Prefer `git pull --rebase` when resolving divergent
   branches to keep a linear history.


---

## Project: Quanto

Quanto es un sistema de análisis financiero personal que procesa extractos
mensuales de Davivienda (cuenta + TC), Davibank (TC), y Nequi. Extrae
movimientos de PDFs oficiales, los categoriza, detecta transferencias
internas entre productos, y genera un dashboard HTML editorial.

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

\`\`\`
quanto/
├── .claude/
│   ├── agents/quanto.md                  ← sub-agente Claude Code
│   └── skills/quanto-extractos/
│       ├── categorias.json               ← diccionario de categorización
│       └── scripts/                      ← pipeline en 9 scripts
├── extractos/YYYY-MM/*.pdf              ← entrada (gitignored)
├── analisis/YYYY-MM/*.json              ← salida procesada (gitignored)
└── dashboard.html                       ← reporte visual (gitignored)
\`\`\`

### Dependencias de sistema

- `pdftotext` (poppler-utils) — binario externo usado por todos los parsers
  vía subprocess. En Fedora/Bazzite: `sudo rpm-ostree install poppler-utils`.
- Python 3.14 gestionado por uv.
- No hay dependencias pip — todo el código usa stdlib.

### Comandos comunes

\`\`\`bash
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
\`\`\`

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

