# Travel Aggregator

## About the project

Travel Aggregator is a multimodal trip planner. It connects several modes of
transportation (car, plane, train, public bus, Greyhound, and rideshare)
to find the most efficient path to a destination. Our team built it with a Django
backend and an HTML, CSS, and JavaScript frontend.

A trip is split into **legs**, one for each mode of transport, and the legs are combined
into a single multimodal route. For example, a journey might start with a car ride to an
airport, continue by plane, and finish by bus. The goal is the best overall combination,
not just the best option within one mode.

**What a user can do**

- Enter a starting address and a destination, with address suggestions as they type.
- Pick a travel date and which modes to consider.
- Choose whether to rank results by lowest cost or by fastest trip.
- See the resulting routes, made up of their legs, on a results page with an interactive map.
- Come back later: recent searches are remembered for up to 30 days in the same browser, without needing an account.

**Where the data comes from**

Each leg draws on a data source for its mode:

| Mode | Source | Notes |
|------|--------|-------|
| Car | OSRM routing | Uses the public demo server by default; set `OSRM_ROUTE_URL` to use another. |
| Plane | Google Flights scraper (`fast-flights`) | Prices can be missing or out of date. |
| Train | Amtrak GTFS timetable | Schedules only, with no fares, and a limited list of stations. |
| Public bus | Transitland and a transit API | Needs `TRANSIT_API_KEY` and `TRANSITLAND_API_KEY`. |
| Greyhound | Unofficial FlixBus/Greyhound endpoint | Currently one traveler and only the Dallas to Houston city IDs. |
| Rideshare | (Needs rework)Planned | (Needs rework)Not connected yet. |

Address suggestions come from Photon, and the map uses Leaflet with OpenStreetMap tiles.
Fares that a provider does not report are shown as unavailable and are never treated as free.

**How it is built**

- Django 5.2 with SQLite. Saved searches are stored on the server in the Django session table.
- (Needs rework)A `planner` app holds the pages and the provider integrations. A `routes` app keeps the original JSON API endpoints (`/api/search/`, `/api/flights/`, `/api/saved/`, and others).
- (Needs rework)The provider scripts are kept in a `legacy/` folder and called through `planner/services.py`.
- It runs in Docker with gunicorn behind Caddy, as described below.

This is a prototype. Several providers rely on scraping or free public services with usage limits,
so results can be slow, incomplete, or temporarily unavailable.

---

# Deployment guide: running the app in Docker

The Docker folder runs the Django app on a server using Docker. The `app` container
clones the repo from GitHub, installs `requirements.txt`, runs migrations, and
restarts the app automatically when new commits are pushed.

```
Visitors --HTTPS--> Cloudflare --tunnel--> cloudflared --> Caddy --> Django (gunicorn)
                                                  \-----> Dozzle (optional log viewer)
```

| Container     | Purpose |
|---------------|---------|
| `app`         | Clones the repo, installs requirements, runs `migrate` and `collectstatic`, starts gunicorn, and pulls new commits on an interval. |
| `caddy`       | Web server in front of Django. Serves static files and forwards all other requests to gunicorn. |
| `cloudflared` | Cloudflare Tunnel. Connects outbound to Cloudflare, so no router port forwarding is needed. Provides HTTPS. |
| `dozzle`      | Optional web page for viewing container logs, protected by Cloudflare Access. |

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Builds the `app` image (Python, git, a virtualenv). |
| `entrypoint.sh` | Clone, auto-pull, install, and start logic for the `app` container. |
| `docker-compose.yml` | Defines the containers. |
| `Caddyfile` | Caddy web server configuration. |
| `.env.example` | Template for the private `.env` file. |
| `DOCKER_COMMANDS.txt` | Command cheat sheet. |

## Requirements

- A machine with Docker and the Docker Compose plugin (`docker compose version` should work).
- The repository URL and the branch to deploy. The branch must be pushed to GitHub.
- For a private repository, a GitHub access token.
- A Django secret key.
- For public hosting: a Cloudflare account, a domain on it, and a tunnel. Not needed for local testing.
- Any API keys the app reads from environment variables.

## Setup

Run all commands from this folder.

### 1. Create the private `.env` file

```bash
cp .env.example .env
```

`.env` holds all secrets, API keys, and settings, and must never be committed.

Docker names its volumes after the folder this stack runs from. Always run
Compose from the same folder, or the stored database will not be found.

### 2. GitHub token (private repositories only)

Create a personal access token on GitHub (Settings, Developer settings,
Personal access tokens). A classic token with the `repo` scope works for any
repository you can access. A fine-grained token with read access to
*Contents* works only for repositories owned by your own account or
organization. Set an expiration, and put the token in `.env` as `GITHUB_TOKEN`.

### 3. Django secret key

```bash
python3 -c "import secrets; print(secrets.token_urlsafe(60))"
```

Put it in `.env` inside single quotes: `DJANGO_SECRET_KEY='...'`. Use the same
key permanently; changing it signs out existing sessions.

### 4. Cloudflare Tunnel

1. In Cloudflare Zero Trust, go to Networks, Tunnels, and create a tunnel of type Cloudflared.
2. Copy the token, which is only the long string starting with `eyJ`, not the surrounding install command. Put it in `.env` as `TUNNEL_TOKEN`, with no quotes or spaces.
3. On the tunnel's Routes tab, add published applications:

   | Domain | Service |
   |--------|---------|
   | `your-domain.example` | `http://caddy:80` |
   | `logs.your-domain.example` (optional) | `http://dozzle:8080` |

   Saving a route creates its DNS record.

Use a single tunnel for all hostnames. A second tunnel needs its own running
`cloudflared`. DNS records for a tunnel point to the Tunnel ID (not a Replica
ID) followed by `.cfargotunnel.com`.

### 5. Configure `.env`

| Variable | Meaning |
|----------|---------|
| `REPO_URL`, `BRANCH` | Repository to clone and the branch to run. |
| `PROJECT_DIR` | Folder inside the repo that contains `manage.py`. |
| `GITHUB_TOKEN` | Only for private repositories. |
| `PULL_INTERVAL` | Seconds between checks for new commits. `0` pulls only at startup. |
| `TUNNEL_TOKEN` | Cloudflare tunnel token from step 4. |
| `START_CMD` | Command that migrates, collects static files, and starts gunicorn. Use the value in `.env.example`. |
| `DJANGO_SECRET_KEY` | From step 3. Keep the single quotes. |
| `DJANGO_DEBUG` | `0` in production, `1` for local testing. |
| `DJANGO_ALLOWED_HOSTS` | Comma-separated host names, with no spaces. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | Comma-separated origins including the scheme, such as `https://your-domain.example`. |
| `DJANGO_TRUST_PROXY` | `1` when behind Cloudflare and Caddy, so Django trusts the forwarded protocol. |
| `DJANGO_SSL_REDIRECT` | `0` when Cloudflare already forces HTTPS. Together with `DJANGO_TRUST_PROXY`, this prevents redirect loops. |
| API keys | Any additional keys the app reads from the environment. |

### 6. Start

```bash
docker compose up -d --build
docker compose ps
docker compose logs -f app
```

The first start takes a few minutes while packages install. The app is ready
when the log shows `Listening at: http://0.0.0.0:8000`.

### 7. Optional: log viewer

Add a Dozzle service to `docker-compose.yml`, at the same indentation as `app:`:

```yaml
  dozzle:
    image: amir20/dozzle:latest
    restart: unless-stopped
    environment:
      - DOZZLE_NO_ANALYTICS=true
      # Show only this project's containers. The value is the Compose project name,
      # which defaults to the lowercase name of the folder containing docker-compose.yml.
      - DOZZLE_FILTER=label=com.docker.compose.project=<project-name>
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
```

Protect it before exposing it:

1. In Zero Trust, go to Access, Applications, and add a Self-hosted application for the logs hostname.
2. Add an Allow policy using the Emails rule, listing the permitted users.
3. Under Settings, Authentication, enable One-time PIN and select it for the application.
4. Add the logs route to the tunnel (step 4), then run `docker compose up -d`.

Logs can contain visitor details and error output, so restrict access to people who need it.

## Everyday use

| Task | Command |
|------|---------|
| Start or apply changes | `docker compose up -d` |
| Status | `docker compose ps` |
| Follow the app log | `docker compose logs -f app` |
| Stop, keeping data | `docker compose stop` |
| Rebuild | `docker compose up -d --build` |
| Shell inside the app | `docker compose exec app bash` |

- **Deploying code:** push to the configured branch. The server pulls it within one `PULL_INTERVAL` and restarts the app.
- **Changing `.env` or `docker-compose.yml`:** run `docker compose up -d`.
- **Changing the `Caddyfile`:** it is mounted as a single file, so a plain restart can keep the old copy. Run `docker compose up -d --force-recreate caddy`, then `docker compose up -d`.
- After any command that names a single service, finish with a plain `docker compose up -d` so nothing stays stopped.

## Local testing

Use a local `.env` with:

```
DJANGO_DEBUG=1
DJANGO_ALLOWED_HOSTS=localhost,127.0.0.1
```

- `DJANGO_DEBUG=1` disables the forced HTTPS redirect and secure-only cookies, which cannot work over plain `http://localhost`.
- Start only the containers you need: `docker compose up -d app caddy`. Leave out `cloudflared`, which restarts continuously without a valid token.
- Open the port Caddy publishes in `docker-compose.yml` (the number on the left of the `ports` mapping).
- If a form returns 403, add `DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:<port>`, including the scheme and port.
- Without Docker: install `requirements.txt`, place `.env` next to `manage.py`, and run `python manage.py runserver`.

## Troubleshooting

| Symptom | Cause and fix |
|---------|---------------|
| `Clone FAILED` in the app log | Wrong `REPO_URL` or `BRANCH`, a missing or insufficient token, or an unpushed branch. The log shows git's error. |
| `PROJECT_DIR` not found | The clone failed, or the folder is not on that branch. Check the branch, `PROJECT_DIR`, and that changes are committed and pushed. |
| Stale files after a large restructure | Run `docker compose down -v`, then `docker compose up -d --build`. This deletes the database. |
| Caddy log shows `connection refused` to `app:8000` | gunicorn is not running. Read `docker compose logs app` for the cause (missing package, migration error, or settings error). |
| `400 Bad Request` | The host name is missing from `DJANGO_ALLOWED_HOSTS`. |
| `ERR_TOO_MANY_REDIRECTS` | Set `DJANGO_TRUST_PROXY=1` and `DJANGO_SSL_REDIRECT=0`, and confirm the `Caddyfile` contains its `trusted_proxies` block. |
| 403 on form submissions | `DJANGO_CSRF_TRUSTED_ORIGINS` lacks the site's `https://` origin. |
| Cloudflare Error 1033 | No running connector for that tunnel. Run `docker compose up -d` and check `docker compose logs cloudflared`. A hostname assigned to a different tunnel causes this too. |
| `Provided Tunnel token is not valid` | Wrong `TUNNEL_TOKEN`. Use only the `eyJ...` string on one line, with no quotes. |
| `DNS_PROBE_FINISHED_NXDOMAIN` on some devices | If DNSSEC is enabled in Cloudflare with a mismatched DS record, validating resolvers fail. Disable DNSSEC, and flush local DNS caches. |
| Unstyled page | Stale browser or Cloudflare cache. Hard-refresh, try a private window, and purge Cloudflare's cache. Confirm `collectstatic` ran. |
| Map tiles show "403 Access blocked" | OpenStreetMap requires a Referer. The `Caddyfile` overrides Django's `Referrer-Policy` header to allow it. |
| `address already in use` on a port | Another program holds the port. Stop it, or change the left number in the `ports` mapping. |
| Many `stream ... canceled by remote` lines in the `cloudflared` log | Harmless. Browsers closing live-log or autocomplete requests. |

## Data and backups

The database and cloned code live in Docker volumes. They survive `stop`, `down`,
rebuilds, and automatic updates. They are deleted by `docker compose down -v`,
`docker volume rm`, and by `docker volume prune` or `docker system prune --volumes`
while the stack is stopped.

Back up before risky changes:

```bash
docker compose cp app:/app/<project-dir>/db.sqlite3 ./db-backup.sqlite3
```

## Security

- Do not commit `.env`, tokens, or keys. Keep `.env` in `.gitignore`.
- Do not share tokens or keys in chat, issues, or screenshots. If one leaks, revoke or rotate it.
- Keep `DJANGO_DEBUG=0` on any public server.
- Expose only Caddy, through the tunnel. Do not forward the application ports on a router.
- Keep the log viewer behind Cloudflare Access.
