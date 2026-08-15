# Create the Vestra Intel custom GPT

## Phase A — create the GPT before hosting FIA

1. In ChatGPT on the web, open **Explore GPTs** and select **Create**.
2. Name: **Vestra Intel**.
3. Description: **Public-asset intelligence operator for discovering, correlating, ranking, and researching lawful forgotten-asset and rights opportunities.**
4. Paste `gpt/vestra-intel-instructions.md` into Instructions.
5. Add the prompts from `gpt/conversation-starters.md` as conversation starters.
6. Upload the four files in `gpt/knowledge/` as Knowledge.
7. Enable Web Search. Enable Code Interpreter & Data Analysis if desired for ad-hoc analysis.
8. Keep the GPT private while the backend Action is not connected.

## Phase B — deploy the FIA backend

The Action server must be reachable over public HTTPS.

Minimum environment:

- `FIA_AGENT_API_KEY` — strong random bearer secret.
- `FIA_PUBLIC_BASE_URL` — final public HTTPS origin.
- `FIA_DB_PATH` — preferably a persistent mounted path such as `/data/fia.sqlite3`.
- source-specific credentials only when using those sources.

The included Dockerfile starts `uvicorn fia.api:app` on `$PORT` or 8000.

After deployment verify:

- `https://YOUR-HOST/health`
- `https://YOUR-HOST/gpt/openapi.json`
- `https://YOUR-HOST/privacy`

## Phase C — connect GPT Actions

1. Edit **Vestra Intel** in the GPT editor.
2. Go to **Actions** and select **Create new action**.
3. Import the schema from `https://YOUR-HOST/gpt/openapi.json` or paste that JSON.
4. Authentication: choose **API key**, then **Bearer**.
5. Secret value: the exact server-side `FIA_AGENT_API_KEY`.
6. Privacy policy: `https://YOUR-HOST/privacy`.
7. Test `getVestraStatus` in Preview.
8. Test `getVestraPortfolio`.
9. Test `runVestraResearch` with `execute=false` before any live research execution.
10. Save/update the GPT.

Do not enable Apps in this GPT when using Actions; the GPT editor treats Apps and Actions as mutually exclusive integration modes.
