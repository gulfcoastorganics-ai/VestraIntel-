# Deploy Vestra Intel for GPT Actions

Vestra Intel GPT Actions require a stable public HTTPS backend. The included Dockerfile is platform-neutral and expects persistent storage for the SQLite database.

Required production environment:

```bash
FIA_AGENT_API_KEY=<strong random secret>
FIA_PUBLIC_BASE_URL=https://your-real-hostname.example
FIA_DB_PATH=/data/fia.sqlite3
FIA_USER_AGENT="VestraIntel/1.5 (+your-public-business-contact)"
```

Generate the bearer secret locally:

```bash
python -c 'import secrets; print(secrets.token_urlsafe(48))'
```

Optional source credentials:

```bash
COMPANIES_HOUSE_API_KEY=
COMPANIES_HOUSE_STREAM_KEY=
USPTO_API_KEY=
DATA_GOV_API_KEY=
```

Build locally:

```bash
docker build -t vestra-intel:1.5.0 .
docker run --rm -p 8000:8000 \
  -e FIA_AGENT_API_KEY="$FIA_AGENT_API_KEY" \
  -e FIA_PUBLIC_BASE_URL="http://localhost:8000" \
  -v "$PWD/data:/data" \
  vestra-intel:1.5.0
```

Production must use HTTPS. Keep `/data` persistent across deployments.
