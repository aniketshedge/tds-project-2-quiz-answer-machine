# CI/CD Pipeline – NUC + GitHub Actions + Docker

This document describes how to (re)create the CI/CD setup for this project on an Intel NUC (or any Ubuntu server) using:

- a **self‑hosted GitHub Actions runner** on the NUC,
- **Docker** to build and run the app, and
- an optional **Cloudflare Tunnel** to expose the API over HTTPS.

It assumes the repository is:  
`https://github.com/aniketshedge/tds-project-2-quiz-answer-machine`

> Tip: Use this doc later to rebuild the pipeline from scratch after a clean machine reset.

---

## 1. High‑level pipeline overview

At a high level:

1. Code is pushed to GitHub (usually to the `main` branch).
2. A GitHub Actions **workflow** is triggered.
3. The workflow runs on a **self‑hosted runner** installed on your NUC (labelled `self-hosted`).
4. The runner:
   - checks out the code,
   - builds the Docker image (using `Dockerfile`),
   - runs `docker compose up -d --build` to start/refresh the container.
5. Separately, a **Cloudflare Tunnel** forwards `https://api.yourdomain.com` to `http://localhost:8000` on the NUC, where the FastAPI app is listening inside the container.

---

## 2. Prerequisites

On your **local laptop**:

- Git installed and configured.
- Access to the GitHub repo.

On the **NUC server** (Ubuntu assumed):

- SSH access.
- GitHub CLI (`gh`) installed and logged in (`gh auth login`).
- Ability to install packages with `sudo apt`.

On your **domain provider / Cloudflare**:

- A Cloudflare account with your domain added (for the tunnel).

---

## 3. Prepare the NUC (Docker and tools)

Run these commands **on the NUC**:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y docker.io jq curl
```

Add your user to the `docker` group so you can run `docker` without `sudo`:

```bash
sudo usermod -aG docker $USER
newgrp docker
```

Verify:

```bash
docker ps
```

If this runs without `permission denied`, Docker permissions are set correctly.

---

## 4. Install and register the self‑hosted runner

All of this is done **on the NUC** in your home directory.

### 4.1. Create runner directory and download binaries

```bash
mkdir -p ~/actions-runner
cd ~/actions-runner

curl -o actions-runner-linux-x64-2.314.1.tar.gz \
  -L https://github.com/actions/runner/releases/download/v2.314.1/actions-runner-linux-x64-2.314.1.tar.gz

tar xzf ./actions-runner-linux-x64-2.314.1.tar.gz
```

If a newer runner version is available, you can update the URL to match GitHub’s latest release.

### 4.2. Generate a registration token using `gh`

Because you are logged in with `gh`, you can generate a short‑lived registration token without visiting the web UI.

```bash
REG_TOKEN=$(gh api --method POST \
  -H "Accept: application/vnd.github+json" \
  /repos/aniketshedge/tds-project-2-quiz-answer-machine/actions/runners/registration-token \
  | jq -r .token)

echo "Token acquired: $REG_TOKEN"
```

### 4.3. Configure the runner

From inside `~/actions-runner`:

```bash
./config.sh \
  --url https://github.com/aniketshedge/tds-project-2-quiz-answer-machine \
  --token "$REG_TOKEN" \
  --name my-nuc-runner \
  --unattended \
  --labels self-hosted
```

You can change `--name` if you prefer a different identifier.

### 4.4. Install and start the runner as a service

```bash
sudo ./svc.sh install
sudo ./svc.sh start
```

Check status:

```bash
sudo ./svc.sh status
```

It should show the service as active/running.

At this point, the GitHub repo should show a self‑hosted runner under  
**Settings → Actions → Runners**.

---

## 5. Create the `.env` file on the NUC

The app expects a `.env` file (not committed to Git). This file must live in the repo directory on the runner.

After the first workflow run, the repo will be cloned under:

```text
~/actions-runner/_work/tds-project-2-quiz-answer-machine/tds-project-2-quiz-answer-machine
```

You can also create the `.env` earlier and move it later. To edit/create it:

```bash
cd ~/actions-runner/_work/tds-project-2-quiz-answer-machine/tds-project-2-quiz-answer-machine
nano .env
```

Example contents (adjust as needed):

```env
OPENAI_API_KEY=sk-your-actual-key-here
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-5-nano

STUDENT_SECRET=your_secret_string
```

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

> Important: This `.env` lives **only** on the NUC and is **not** tracked in Git.

---

## 6. Example GitHub Actions workflow

The workflow file (stored in the repo) tells GitHub what to do on each push. A simple deployment workflow could look like this:

Create `.github/workflows/deploy-nuc.yml` in the repo with:

```yaml
name: Deploy to NUC

on:
  push:
    branches: [ main ]

jobs:
  deploy:
    runs-on: self-hosted  # uses the NUC runner

    steps:
      - name: Check out code
        uses: actions/checkout@v4

      - name: Log in to Docker (optional, if using a registry)
        if: false  # set to true and configure if you push to a registry
        run: |
          echo "${{ secrets.DOCKER_PASSWORD }}" | docker login \
            -u "${{ secrets.DOCKER_USERNAME }}" --password-stdin

      - name: Build and run with Docker Compose
        run: |
          docker compose down || true
          docker compose up -d --build
```

Key points:

- `runs-on: self-hosted` ensures this job runs on your NUC, not GitHub’s hosted runners.
- The job:
  - pulls the latest code,
  - tears down any existing containers (`docker compose down`),
  - rebuilds and restarts the stack (`docker compose up -d --build`).
- The `.env` already on the NUC is read by `docker compose` when building/running.

You can customize this workflow:

- Add a `concurrency` block to avoid overlapping deployments.
- Add steps to run tests before deployment.
- Add `on: workflow_dispatch:` to allow manual “Deploy” triggers from the Actions tab.

---

## 7. Cloudflare Tunnel for HTTPS access

This step is **optional** but recommended so your API is reachable at a stable HTTPS domain like `https://api.yourdomain.com`.

All commands in this section run **on the NUC**.

### 7.1. Install Cloudflared

```bash
curl -L --output cloudflared.deb \
  https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb

sudo dpkg -i cloudflared.deb
```

### 7.2. Login to Cloudflare

```bash
cloudflared tunnel login
```

Follow the printed URL in a browser (from your laptop), log in, and authorize your domain.

### 7.3. Create and route the tunnel

```bash
cloudflared tunnel create nuc-quiz-tunnel
```

Note the UUID that Cloudflared prints; call it `<UUID>`.

Route it to a subdomain, e.g. `api.yourdomain.com`:

```bash
cloudflared tunnel route dns <UUID> api.yourdomain.com
```

### 7.4. Point the tunnel to the local app

Assuming your FastAPI app inside Docker listens on port `8000`:

```bash
cloudflared tunnel run --url http://localhost:8000 nuc-quiz-tunnel
```

To keep it running in the background, you can:

- Use `nohup`:

  ```bash
  nohup cloudflared tunnel run --url http://localhost:8000 nuc-quiz-tunnel > cloudflared.log 2>&1 &
  ```

- Or configure it as a systemd service (similar to the GitHub runner service).

Once running, `https://api.yourdomain.com/run` will proxy to `http://localhost:8000/run` on the NUC.

---

## 8. Deploying and re‑deploying

With everything set up:

1. Make changes to the code locally.
2. Commit and push to `main`:

   ```bash
   git add .
   git commit -m "Update quiz agent"
   git push origin main
   ```

3. Open the **Actions** tab in GitHub for this repo.
4. You should see the `Deploy to NUC` workflow run, using the self‑hosted runner.
5. When it completes successfully:
   - Docker on the NUC will have built a new image.
   - `docker compose up -d --build` will be running the new version.
   - Your public endpoint (`https://api.yourdomain.com/run`) should serve the latest code.

To redeploy at any time, just push another commit (or manually re‑run the workflow if you added `workflow_dispatch`).

---

## 9. Monitoring and debugging

On the NUC, you can inspect:

- Running containers:

  ```bash
  docker ps
  ```

- Logs for the app container (replace `<container-name>` as needed):

  ```bash
  docker logs -f <container-name>
  ```

- Status of the runner service:

  ```bash
  cd ~/actions-runner
  sudo ./svc.sh status
  ```

- Cloudflare tunnel logs:

  ```bash
  ps aux | grep cloudflared
  # and check any log file you created, e.g. cloudflared.log
  ```

If your CI/CD stops working, common issues include:

- The runner service not running (`svc.sh status`).
- Docker permission issues (user not in `docker` group).
- Cloudflare tunnel not running or misconfigured DNS.
- Invalid environment variables in `.env` (e.g. wrong `STUDENT_SECRET` or API key).

---

## 10. Teardown reference

When you’re done with this project and want to fully remove everything (runner, Docker state, Cloudflare tunnel, etc.), see:

- `docs/cleanup.md`

