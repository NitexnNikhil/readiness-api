# Havet AI Readiness Report API

FastAPI service for generating a candidate readiness report as both HTML and PDF.

## What It Does

- Accepts a readiness JSON payload
- Renders the report template from `templates/readiness_report.html`
- Writes the generated HTML to `output/readiness_report.html`
- Writes the generated PDF to `output/readiness_report.pdf`

## Run Locally

```bash
uvicorn main:app --reload
```

Then open:

- `GET /`
- `POST /generate-readiness-report`

## Request Shape

The API expects a JSON body with these top-level keys:

- `common_intelligence`
- `persona_specific_intelligence`

See [`example.json`](./example.json) for the current sample payload.

## Output Files

After a successful request, the app creates:

- [`output/readiness_report.html`](./output/readiness_report.html)
- [`output/readiness_report.pdf`](./output/readiness_report.pdf)

## Notes

- The HTML template is self-contained, including its CSS.
- The PDF is generated from the rendered HTML.
- If browser-based PDF generation is unavailable, the app falls back to the local PDF renderer.
