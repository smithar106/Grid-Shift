# Deployment

GridShift runs as three Railway services built from this repository. No local Docker
installation is required — Railway builds the images remotely.

| Service | Root directory | Type | Public |
| --- | --- | --- | --- |
| `gridshift-web` | `/apps/web` | Next.js (standalone) | Yes |
| `gridshift-api` | `/apps/api` | FastAPI + SciPy | No — private network only |
| `Postgres` | — | Railway database | No |

The browser only ever talks to the Next.js origin. The route handler at
`apps/web/app/api/v1/[...path]/route.ts` forwards `/api/v1/*` to the API over Railway's
private network, so the API has no public domain and no cross-origin configuration.

```
Browser ──HTTPS──► gridshift-web ──private network──► gridshift-api ──► Postgres
```

## Service settings

Root directory, healthcheck, and start command are **service settings**, not config-as-code.
Railway deprecated `railway.toml` in favour of Infrastructure as Code, so the `railway.toml`
files in each app are retained only as documentation of intent. The authoritative settings:

| Setting | `gridshift-api` | `gridshift-web` |
| --- | --- | --- |
| Root directory | `apps/api` | `apps/web` |
| Builder | Dockerfile | Dockerfile |
| Healthcheck path | `/api/v1/health` | `/api/health` |
| Healthcheck timeout | 120s | 120s |
| Restart policy | `ON_FAILURE`, 5 retries | `ON_FAILURE`, 5 retries |

## Environment variables

`gridshift-api`

| Variable | Value | Notes |
| --- | --- | --- |
| `ENVIRONMENT` | `production` | |
| `PORT` | `8000` | Pinned so the private-network URL is stable |
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` | Reference, resolved by Railway |
| `CORS_ORIGINS` | web origin, comma-separated | Only relevant for direct access; the proxy is same-origin |

`gridshift-web`

| Variable | Value | Notes |
| --- | --- | --- |
| `PORT` | `3000` | |
| `HOSTNAME` | `0.0.0.0` | Required for the standalone server to accept external traffic |
| `API_INTERNAL_URL` | `http://gridshift-api.railway.internal:8000` | Private network address |

## Migrations

`apps/api/scripts/start.sh` runs `alembic upgrade head` before the server binds, retrying
up to 10 times so a cold or still-provisioning database does not fail the deploy. The
server only starts after migrations succeed.

## Recreating this deployment

```bash
railway init --name gridshift
railway add --database postgres
railway add --service gridshift-api
railway add --service gridshift-web

railway service source connect --repo <owner>/Grid-Shift --branch main --service gridshift-api
railway service source connect --repo <owner>/Grid-Shift --branch main --service gridshift-web

# Root directory is not exposed by the CLI; set it through the GraphQL API.
railway api 'mutation($s:String!,$e:String!,$i:ServiceInstanceUpdateInput!){
  serviceInstanceUpdate(serviceId:$s, environmentId:$e, input:$i)
}' --var s='"<api-service-id>"' --var e='"<environment-id>"' \
   --var i='{"rootDirectory":"apps/api","healthcheckPath":"/api/v1/health","healthcheckTimeout":120,"startCommand":"./scripts/start.sh"}'

railway variable set 'ENVIRONMENT=production' 'PORT=8000' \
  'DATABASE_URL=${{Postgres.DATABASE_URL}}' --service gridshift-api --skip-deploys

railway variable set 'PORT=3000' 'HOSTNAME=0.0.0.0' \
  'API_INTERNAL_URL=http://gridshift-api.railway.internal:8000' \
  --service gridshift-web --skip-deploys

railway domain --service gridshift-web
```

Find the service and environment IDs with `railway status --json`.

> **Gotcha:** `railway domain` without a subcommand **creates** a domain. To inspect the
> existing domains use `railway domain list`. Deleting the API's auto-generated public
> domain is what keeps the API private.

## Cost

The Railway Free plan permits three services after the trial, which matches this topology
exactly. The trial provides $5 of credit for 30 days. Monitor usage rather than assuming
the deployment stays free.
