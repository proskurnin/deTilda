# Production Deploy

Production domains:

- `detilda.com`
- `detilda.ru`

Both domains should resolve to the production server `2.26.31.179`.

Production runs on the same host as staging, but uses a separate local app port:

- staging: `127.0.0.1:8000`
- production: `127.0.0.1:8001`

## Current Deploy Model

Staging deploys from the `main` branch.

Production deploys from the `prod` branch.

GitHub Actions workflow:

- `.github/workflows/deploy.yml`

Production runtime files:

- `docker-compose.prod.yml`
- `nginx/prod.conf`
- server-local `.env.prod`

## One-Time Server Bootstrap

Run these steps on the server before the first production deploy.

1. Confirm DNS:

   ```bash
   dig +short detilda.com
   dig +short detilda.ru
   ```

   Both should return:

   ```text
   2.26.31.179
   ```

2. Prepare the production checkout:

   ```bash
   sudo mkdir -p /home/deploy/prod
   sudo chown -R deploy:deploy /home/deploy/prod
   cd /home/deploy/prod
   git clone https://github.com/proskurnin/deTilda.git .
   git fetch origin prod
   git checkout -B prod origin/prod
   ```

3. Create `/home/deploy/.env.prod` or `/home/deploy/secrets/.env.prod`.

   Required values follow the same pattern as staging, but must use production secrets:

   ```bash
   ADMIN_USER=...
   ADMIN_PASSWORD=...
   ```

   Add SMTP values if mail delivery is enabled in production.

4. Start the production container once:

   ```bash
   cd /home/deploy/prod
   cp /home/deploy/.env.prod .env.prod
   chmod 600 .env.prod
   docker compose -f docker-compose.prod.yml up -d --build
   curl -fsS http://127.0.0.1:8001/health
   ```

5. Install the temporary HTTP-only nginx config:

   ```bash
   cd /home/deploy/prod
   sudo cp nginx/prod.bootstrap.conf /etc/nginx/sites-available/detilda.com
   sudo ln -sf /etc/nginx/sites-available/detilda.com /etc/nginx/sites-enabled/detilda.com
   sudo nginx -t
   sudo systemctl reload nginx
   ```

6. Issue the production certificate:

   ```bash
   sudo certbot --nginx -d detilda.com -d detilda.ru
   ```

   The canonical certificate path expected by `nginx/prod.conf` is:

   ```text
   /etc/letsencrypt/live/detilda.com/
   ```

7. Install the final SSL nginx config:

   ```bash
   cd /home/deploy/prod
   sudo cp nginx/prod.conf /etc/nginx/sites-available/detilda.com
   sudo nginx -t
   sudo systemctl reload nginx
   ```

8. Check production externally:

   ```bash
   curl -fsS https://detilda.com/health
   curl -fsS https://detilda.ru/health
   ```

## GitHub Secrets

Production deploy requires these GitHub repository secrets:

- `PROD_HOST`
- `PROD_USER`
- `PROD_SSH_KEY`

For the current server:

- `PROD_HOST` should be `2.26.31.179`;
- `PROD_USER` should be the SSH user that owns `/home/deploy/prod`.

## Release Flow

1. Merge or cherry-pick the release commit into `prod`.

   ```bash
   git checkout prod
   git merge main
   git push origin prod
   ```

2. GitHub Actions runs tests.

3. If tests pass, `deploy-prod`:

   - connects to `/home/deploy/prod`;
   - preserves server-local `.env.prod`;
   - checks out `origin/prod`;
   - rebuilds `docker-compose.prod.yml`;
   - installs `nginx/prod.conf`;
   - reloads nginx;
   - checks `http://127.0.0.1:8001/health`.

4. After deploy, verify the public health endpoints:

   ```bash
   curl -fsS https://detilda.com/health
   curl -fsS https://detilda.ru/health
   ```

## Known Requirements

- The `prod` branch must exist on GitHub before automatic production deploy can run.
- The first deploy requires manual certificate bootstrap because `nginx/prod.conf` references real Let's Encrypt files.
- Staging and production must not share the same local app port.
