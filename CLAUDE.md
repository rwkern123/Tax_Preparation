# Tax Preparation Project Context

## Product shape

This project has exactly two user-facing applications:

- `portal/` is the client portal.
- `preparer/` is the tax-preparer portal.

`src/` is their shared tax-processing engine. Do not add another CLI or web
dashboard entry point. New extraction behavior should be exposed to the portals
through `preparer/parser_bridge.py` or a focused shared service.

## Entry points

```powershell
python run_portal.py
python run_preparer.py
```

Both bind to localhost by default. `launch_portal.bat` and
`launch_preparer.bat` are the Windows launchers.

## Architecture

- `src/classify.py` classifies uploaded documents.
- `src/extract/` contains local and optional Azure parsers.
- `src/models.py` defines normalized extraction dataclasses.
- `src/tax_calculator.py` provides federal tax estimates used by the preparer portal.
- `preparer/parser_bridge.py` is the portal-facing adapter for the shared parsers.
- `portal/database.py` stores client accounts, questionnaires, uploads, and interviews.
- `preparer/database.py` stores parsed documents, overrides, and manual entries.
- `preparer/form_1040_filler.py` fills and merges supported federal PDF forms.

## Principles

- Keep processing local unless Azure is explicitly enabled.
- Never commit `portal_data/`, credentials, uploaded documents, or unredacted PII.
- Web requests must not install packages or otherwise mutate the Python environment.
- Keep parser results normalized through the shared dataclasses.
- Add parser and portal-integration tests when supporting a new form.

## Testing

```powershell
python -m pytest -q
```

Known limitations and future work are tracked in `ideas/roadmap.md`.
