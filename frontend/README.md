# Evalflow Frontend

Dark analytics interface for the LLM Evaluation Platform. It uses the existing
FastAPI registration, JWT login, project, dataset, dataset-item, provider
credential, model-variant, and evaluation-run endpoints.

The current UI supports project selection plus creating, editing, and deleting
datasets and their test cases. Every test case stores an external ID, input
prompt, expected output, and evaluation keywords.

Datasets can also be imported from `.json`, `.jsonl`, or `.ndjson`. The upload
dialog includes a downloadable template; the backend validates the complete
file and saves the dataset plus all test cases atomically.

## Local development

```powershell
Copy-Item .env.example .env.local
npm install
npm run dev
```

The FastAPI backend must be running at `http://127.0.0.1:8000`. Override
`NEXT_PUBLIC_API_URL` in `.env.local` when the API uses another origin.

## Checks

```powershell
npm run build
npm test
npm run lint
```

JWT access tokens are stored in `sessionStorage`, so closing the browser tab
ends the local frontend session. Provider keys are submitted to the backend,
encrypted at rest, masked in every later response, and never stored in browser
storage. Users manage them from the **AI Providers** workspace and attach a
credential to each model variant.
