# Deploying Cosign on Google Cloud (Compute Engine VM)

Cosign runs each agent task in a **fresh Docker container** (the sandbox), via the host
docker socket. Managed serverless (Cloud Run) can't provide that, so the clean target is a
**single Compute Engine VM** running the existing `docker-compose`, fronted by **Caddy**
(auto-TLS) on a free **`sslip.io`** hostname (no domain purchase needed).

> What works where: a VM keeps **both flows**. Cloud Run would break Flow B (the sandbox /
> issue→PR), so it's not used here.

## 0. Prerequisites (laptop)
```bash
gcloud auth login
gcloud config set project <PROJECT_ID>
gcloud services enable compute.googleapis.com
export ZONE=us-central1-a
```
You also need a **GitHub OAuth App** and an **LLM key** (Anthropic and/or Groq).

## 1. Static IP + hostname
```bash
gcloud compute addresses create cosign-ip --region=${ZONE%-*}
export VM_IP=$(gcloud compute addresses describe cosign-ip --region=${ZONE%-*} --format='value(address)')
export COSIGN_HOST=cosign.${VM_IP//./-}.sslip.io       # e.g. cosign.34-1-2-3.sslip.io
```

## 2. Firewall (80/443; SSH allowed by default)
```bash
gcloud compute firewall-rules create cosign-web --allow=tcp:80,tcp:443 --target-tags=cosign-demo
```

## 3. Create the VM (installs Docker on first boot)
```bash
gcloud compute instances create cosign-demo \
  --zone=$ZONE --machine-type=e2-standard-2 \
  --image-family=ubuntu-2204-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=50GB --address=$VM_IP --tags=cosign-demo \
  --metadata=startup-script='#!/bin/bash
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker $(getent passwd 1000 | cut -d: -f1)'
sleep 60
```

## 4. Ship the code to the VM
```bash
# from your local checkout
tar --exclude='./.git' --exclude='node_modules' --exclude='.venv' --exclude='.next' \
    --exclude='infra/.env' --exclude='infra/secrets' --exclude='infra/Caddyfile' \
    -czf /tmp/cosign.tgz .
gcloud compute scp /tmp/cosign.tgz cosign-demo:~/cosign.tgz --zone=$ZONE
gcloud compute ssh cosign-demo --zone=$ZONE --command 'mkdir -p cosign && tar -xzf cosign.tgz -C cosign'
```

## 5. Configure + launch (on the VM)
```bash
gcloud compute ssh cosign-demo --zone=$ZONE
cd ~/cosign/infra
export COSIGN_HOST=cosign.$(curl -s ifconfig.me | tr '.' '-').sslip.io

cp .env.example .env
../scripts/gen-keys.sh

# public URLs + prod settings
sed -i "s#^NEXT_PUBLIC_API_BASE_URL=.*#NEXT_PUBLIC_API_BASE_URL=https://$COSIGN_HOST/api#" .env
sed -i "s#^WEB_BASE_URL=.*#WEB_BASE_URL=https://$COSIGN_HOST#" .env
sed -i "s#^GITHUB_OAUTH_REDIRECT_URL=.*#GITHUB_OAUTH_REDIRECT_URL=https://$COSIGN_HOST/api/auth/github/callback#" .env
sed -i "s#^LLM_ROUTING_CONFIG=.*#LLM_ROUTING_CONFIG=config/llm-routing.yaml#" .env
grep -q '^COOKIE_SECURE=' .env || echo "COOKIE_SECURE=true" >> .env

# then EDIT .env to fill: GITHUB_OAUTH_CLIENT_ID/SECRET, ANTHROPIC_API_KEY (full ~108-char key),
# and (optional) DEMO_USER_CAP_USD=0.50 + DEMO_DEFAULT_PROVIDER=anthropic
nano .env

# Caddy reverse proxy (single host, /api/* -> api, /* -> web)
cat > Caddyfile <<EOF
$COSIGN_HOST {
    encode gzip
    handle_path /api/* {
        reverse_proxy cosign-api:8080 { flush_interval -1 }
    }
    reverse_proxy cosign-web:3000
}
EOF

# bring up data stores + migrations, then build the sandbox image + all app services + Caddy
../scripts/setup-dev.sh
docker build -f sandbox.Dockerfile -t cosign/sandbox:latest .
export COMPOSE_PROFILES=app,demo
docker compose up -d --build
```

## 6. Register the OAuth callback
In your GitHub OAuth App set:
- **Homepage:** `https://$COSIGN_HOST`
- **Authorization callback URL:** `https://$COSIGN_HOST/api/auth/github/callback`

## 7. Verify
```bash
curl -sS https://$COSIGN_HOST/api/health     # {"status":"ok",...}
```
Open `https://$COSIGN_HOST` → sign in → run both flows. A transient `cosign-sbx-*` container
appears during a Flow B run (`docker ps`).

---

## Updating a running deployment

```bash
# 1. (laptop) re-sync current code — never overwrites .env / secrets / Caddyfile
tar --exclude='./.git' --exclude='node_modules' --exclude='.venv' --exclude='.next' \
    --exclude='infra/.env' --exclude='infra/secrets' --exclude='infra/Caddyfile' \
    -czf /tmp/cosign.tgz .
gcloud compute scp /tmp/cosign.tgz cosign-demo:~/cosign.tgz --zone=$ZONE
gcloud compute ssh cosign-demo --zone=$ZONE --command 'tar -xzf cosign.tgz -C cosign'

# 2. (VM) apply any new migration, then rebuild the app services
cd ~/cosign/infra
for f in postgres/migrations/*.sql; do docker compose exec -T postgres psql -U cosign -d cosign < "$f" 2>/dev/null; done
export COMPOSE_PROFILES=app,demo
docker compose up -d --build --force-recreate cosign-api cosign-worker cosign-web
```
- Web changes need `--build` (`NEXT_PUBLIC_*` is baked at build time).
- `.env` changes need `--force-recreate` on that service (it re-reads the env file).
- Hard-refresh the browser (`Ctrl+Shift+R`) — the web bundle is client-cached.
- If `docker` needs `sudo`, run `sudo usermod -aG docker $USER` once and re-SSH so rebuilds don't silently no-op.

## Cost & teardown
`e2-standard-2` ≈ $1.6/day. When done:
```bash
gcloud compute instances delete cosign-demo --zone=$ZONE
gcloud compute addresses delete cosign-ip --region=${ZONE%-*}
gcloud compute firewall-rules delete cosign-web
```
