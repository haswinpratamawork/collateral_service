# Listing Extractor API

A small, self-contained HTTP service: given a **Rumah123 listing URL**, it returns the
listing's **luas tanah**, **luas bangunan**, **kode pos**, and **kelurahan**.

- Luas tanah / luas bangunan come straight from the listing page (parsed by the bundled
  `scraper` package).
- Kode pos / kelurahan are **not** in Rumah123's data — they're derived by **reverse
  geocoding** the listing's latitude/longitude via the **Google Maps Geocoding API**.
- Listings with obfuscated/missing coordinates (~6%) return `null` kode_pos/kelurahan
  (we never guess).

This repo is standalone: it vendors only the slice of the scraper the API needs (fetch +
parse + normalize). There is **no database and no CLI** — it is purely a request/response
API for enriching individual listing URLs on demand.

## Layout

```
.
├── api/                 FastAPI app (endpoints, service, geocoder, response model)
│   ├── main.py          GET /health, GET /extract
│   ├── service.py       fetch + parse the listing, then geocode its coordinates
│   ├── geocode.py       Google Maps reverse geocoding -> kode pos + kelurahan
│   ├── models.py        ExtractResult response model
│   ├── run_api.sh        launcher (uvicorn)
│   └── Dockerfile
├── scraper/             vendored fetch/parse/normalize (no db, no CLI)
├── tests/               DB-free tests (api + parsing + config + fetcher) + fixtures
├── requirements.txt     pinned runtime deps
└── pyproject.toml
```

## Setup

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt          # pinned runtime deps
# or for local dev (editable + test tools): pip install -e ".[dev]"

cp .env.example .env
# then add your key to .env:
#   GOOGLE_MAPS_API_KEY=AIza...
```

The key is read from `.env` automatically (via `python-dotenv`) when the app starts.

## Run

```bash
./api/run_api.sh                 # serve on 0.0.0.0:8030 with auto-reload (dev)
./api/run_api.sh 127.0.0.1 8030  # custom host + port (positional args)
RELOAD=0 ./api/run_api.sh        # production mode (no auto-reload)
```

It picks up the project `.venv` automatically and warns if `GOOGLE_MAPS_API_KEY` is empty.

**Arguments / environment variables:**

| | Default | Meaning |
|---|---------|---------|
| arg 1 / `HOST` | `0.0.0.0` | bind host |
| arg 2 / `PORT` | `8030` | bind port |
| `RELOAD` | `1` | `1` = auto-reload on code change (dev); `0` = production |

Or run uvicorn directly without the script:

```bash
uvicorn api.main:app --reload --port 8030
```

## Docker

The Dockerfile lives in `api/` but needs the whole repo as build context (it copies both
`scraper/` and `api/`), so **build from the repo root**:

```bash
docker build -f api/Dockerfile -t collateral_service .
docker run --env-file .env -p 8030:8030 collateral_service
```

- `--env-file .env` loads the key from your local `.env` at **runtime** (plain `docker run`
  does not auto-read `.env` the way Compose does). The key is never baked into the image —
  `.env` is excluded from the build context via `.dockerignore`.
  - Prefer an explicit value? `-e GOOGLE_MAPS_API_KEY=AIza...` still works and overrides.
- Override the port with `-e PORT=8030` (and map it: `-p 8030:8030`).
- Runs as a non-root user, with a `/health` HEALTHCHECK.

Run it **detached** and manage it:

```bash
docker run -d --name collateral_service --restart unless-stopped \
  --env-file .env -p 8030:8030 collateral_service

docker ps                          # status (health)
docker logs -f collateral_service  # follow logs
docker stop collateral_service     # stop
docker rm -f collateral_service    # remove
```

## Use

```bash
curl "http://localhost:8030/extract?url=https://www.rumah123.com/properti/jakarta-pusat/hos41138420/"
```

```json
{
  "luas_tanah": 294.0,
  "luas_bangunan": 482.0,
  "kode_pos": "10430",
  "kelurahan": "Kenari"
}
```

Interactive docs: http://localhost:8030/docs · Health check: `GET /health`

### Postman

Import [`collateral_scrapping.postman_collection.json`](./collateral_scrapping.postman_collection.json)
(File → Import). It has the `/health` and `/extract` requests plus example responses. Set the
collection variables `base_url` (default `http://localhost:8030`) and `listing_url`.

## Responses

| Status | Meaning |
|--------|---------|
| 200 | OK (fields may be null if coordinates were unavailable) |
| 400 | `url` is not a rumah123.com listing URL |
| 422 | listing page could not be parsed |
| 502 | listing page could not be fetched |
| 500 | `GOOGLE_MAPS_API_KEY` not set |

## Tests

```bash
pip install -e ".[dev]"
pytest
```

The bundled tests parse saved HTML fixtures and use a fake geocoder — **no live HTTP and no
database** required.
