# verifAi — Frontend
React + Vite frontend for the verifAi citation verification platform.

## Requirements

- Node.js v18 or higher
- npm

## Setup 

```bash
cd frontend/app
npm install
```

## Environment setup (local backend)

To connect to a locally running backend, create a `.env.local` file inside `frontend/app`:

```bash
cat > .env.local <<'ENV'
VITE_API_BASE_URL=http://127.0.0.1:8000
ENV
```

## Run locally

```bash
npm run dev
```

Then open [http://localhost:5173](http://localhost:5173) in browser.

## Build for production

```bash
npm run build
```

## Deployment

The frontend is deployed on [Render](https://render.com) and is automatically deployed on every push to the `main` branch.

## Environment

The backend API URL is configured in `src/api.js`. It points to the Railway backend by default.
