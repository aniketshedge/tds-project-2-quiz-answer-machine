# Cleanup Guide – Removing the Quiz Answer Machine from Your NUC

This document explains how to **completely remove** the quiz deployment from your NUC and GitHub once the project is over.

It assumes you followed the deployment steps you shared (self‑hosted GitHub runner, Docker, Cloudflare Tunnel, etc.).

You do **not** have to do everything at once. You can work section by section.

---

## 0. Overview – What we will remove

We will clean up:

- The **GitHub Actions self‑hosted runner** on your NUC.
- The runner’s **cloned repo and work directories**.
- Any **Docker containers/images/volumes** related to this project.
- Your `.env` and other local **secrets**.
- The **Cloudflare Tunnel** (nuc-quiz-tunnel) and related DNS.
- Optional: any **GitHub workflow triggers** that reference the self‑hosted runner.
- Optional: **GitHub CLI authentication** or PATs used only for this project.

Do these steps **on the NUC**, except where noted as GitHub web UI.

---

## 1. Stop and remove the GitHub self‑hosted runner (NUC)

You originally did:

- `mkdir actions-runner && cd actions-runner`
- Downloaded the runner tarball and extracted it.
- Ran `./config.sh ...`
- Installed it as a service: `sudo ./svc.sh install` + `sudo ./svc.sh start`.

Now we reverse that.

### 1.1. Go to the runner directory

On the NUC:

```bash
cd ~/actions-runner
```

If you used a different path, adjust accordingly.

### 1.2. Stop and uninstall the runner service

```bash
sudo ./svc.sh stop
sudo ./svc.sh uninstall
```

You can confirm it is gone:

```bash
sudo ./svc.sh status
```

It should now say the service is not installed or not running.

### 1.3. Unregister the runner from the GitHub repo

This disconnects it from your repository’s Actions configuration.

You have two options:

#### Option A – Via GitHub Web UI (simplest)

1. Go to your repo on GitHub:  
   `https://github.com/aniketshedge/tds-project-2-quiz-answer-machine`
2. Click **Settings** → **Actions** → **Runners** → **Self‑hosted runners**.
3. You should see your runner (e.g. `my-nuc-runner`).
4. Click it, then choose **Remove** / **Delete**.

#### Option B – Via GitHub CLI (advanced)

1. On the NUC, list runners:

   ```bash
   gh api /repos/aniketshedge/tds-project-2-quiz-answer-machine/actions/runners | jq .
   ```

2. Note the `id` of your self‑hosted runner.

3. Delete it:

   ```bash
   RUNNER_ID=<the-id-you-noted>
   gh api --method DELETE \
     /repos/aniketshedge/tds-project-2-quiz-answer-machine/actions/runners/$RUNNER_ID
   ```

Use either A or B (not both). After this, the repo shouldn’t show any self‑hosted runners.

### 1.4. Remove the runner files and work directory

Still on the NUC:

```bash
cd ~
rm -rf actions-runner
```

This deletes:

- the runner binaries (`config.sh`, `svc.sh`, etc.),
- the `_work` directory with cloned repositories.

If you want to be extra careful, you can first check what’s inside:

```bash
ls ~/actions-runner
ls ~/actions-runner/_work
```

Once you are sure you no longer need any of that code, you can safely delete.

---

## 2. Remove Docker containers, images, and volumes

The CI/CD pipeline likely built a Docker image (e.g. `tds-project-2-quiz-answer-machine`) and may be running containers.

### 2.1. Stop and remove containers

List running containers:

```bash
docker ps
```

If you see a container for this project (look at the `IMAGE` or `NAMES` column), stop and remove it:

```bash
docker stop <container-name-or-id>
docker rm <container-name-or-id>
```

If you used `docker compose` on the NUC manually, from this repo, you can also run:

```bash
cd /path/to/tds-project-2-quiz-answer-machine
docker compose down
```

### 2.2. Remove images (optional but recommended)

List images:

```bash
docker images
```

Look for images named something like `tds-project-2-quiz-answer-machine` or similar. Remove them:

```bash
docker rmi <image-id-or-name>
```

If Docker says an image is “in use”, double‑check you stopped/removed all containers in step 2.1.

### 2.3. Clean up dangling data (optional)

To reclaim disk space:

```bash
docker system prune
```

You can add `-a` to also remove unused images, but read the prompt carefully so you don’t delete images you still need for other projects.

---

## 3. Remove secrets and configuration files

### 3.1. Delete `.env` and other secrets on the NUC

On the NUC, locate your cloned repo (if any still exists) or the work directory, and remove the `.env` file:

```bash
cd /path/to/tds-project-2-quiz-answer-machine
rm -f .env
```

If the repo only ever lived inside `~/actions-runner/_work/...`, it was already deleted when you removed `actions-runner`. If you cloned it separately elsewhere, remove any `.env` copies there as well.

Also check for any other files where you might have accidentally stored keys (for example, shell history or ad‑hoc scripts). At minimum:

```bash
history | grep OPENAI
history | grep STUDENT_SECRET
```

If you see secrets in your shell history, consider clearing or truncating it:

```bash
history -c
```

(Be aware this clears your whole history, not just one line.)

### 3.2. Revoke API keys if they were dedicated to this project

If you created a special **OpenAI API key** just for this project, you can now revoke it in the provider’s UI.

Similarly, if you created a dedicated **GitHub Personal Access Token (PAT)** just for this NUC/runner:

- Go to: https://github.com/settings/tokens
- Find the token and delete/revoke it.

### 3.3. Optional: log out of GitHub CLI

If you used `gh auth login` on the NUC, and you no longer want this machine to have GitHub access:

```bash
gh auth logout
```

This step is optional, but good hygiene if the NUC will be repurposed or shared.

---

## 4. Remove the Cloudflare Tunnel and DNS

You created a tunnel called `nuc-quiz-tunnel` and routed `api.yourdomain.com` to it.

We now remove both the tunnel and any running tunnel processes.

### 4.1. Stop any running tunnel

If you started the tunnel manually like this:

```bash
cloudflared tunnel run --url http://localhost:8000 nuc-quiz-tunnel
```

You can stop it by:

- Pressing `Ctrl+C` in that terminal, or
- If it is running in the background, find the process:

  ```bash
  ps aux | grep cloudflared
  ```

  Then kill it:

  ```bash
  kill <pid>
  ```

If you installed Cloudflared as a system service, stop and disable it:

```bash
sudo systemctl stop cloudflared
sudo systemctl disable cloudflared
```

### 4.2. Delete the tunnel (Cloudflare UI)

In the Cloudflare dashboard (web UI):

1. Go to your domain.
2. Navigate to **Zero Trust** / **Tunnels** (or “Access → Tunnels”, depending on UI version).
3. Find the tunnel named `nuc-quiz-tunnel`.
4. Delete/remove it.

Also remove the DNS route (CNAME/record) for `api.yourdomain.com` if it was created by the tunnel setup.

### 4.3. Optional: uninstall `cloudflared` from the NUC

You installed it via:

```bash
curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
sudo dpkg -i cloudflared.deb
```

To remove it:

```bash
sudo apt remove -y cloudflared
rm -f cloudflared.deb
```

Also consider removing any leftover config:

```bash
rm -rf ~/.cloudflared
```

---

## 5. Disable or remove GitHub workflows (repository side)

If your repo has a workflow (for example, `.github/workflows/deploy-staging.yml`) that targets the self‑hosted runner, you have two options:

1. **Disable** the workflow from the GitHub UI:
   - Go to the repo → **Actions**.
   - Click the workflow.
   - Use the “Disable workflow” option.

2. **Edit or delete** the workflow file in the repo:
   - Remove or modify any `runs-on: self-hosted` entries.
   - Remove any `on: schedule:` blocks if you no longer want scheduled runs.

This won’t affect your NUC directly, but it prevents future Actions runs from expecting a runner that no longer exists.

---

## 6. Optional: Remove Docker and supporting tools from the NUC

If this NUC is used only for this project and you want to fully reset it, you can remove Docker and helper tools (`jq`, etc.). **Do this only if you are sure you don’t need them for anything else.**

```bash
sudo apt remove -y docker.io jq
sudo apt autoremove -y
```

Also consider removing any leftover Docker data:

```bash
sudo rm -rf /var/lib/docker
```

Be careful: this deletes all Docker images/containers on the machine, not just for this project.

---

## 7. Quick checklist

Use this checklist to confirm you’re fully cleaned up:

- [ ] `actions-runner` folder removed from the NUC.
- [ ] Self‑hosted runner no longer appears under **Settings → Actions → Runners** for the repo.
- [ ] No project containers are running (`docker ps` is clean, or only shows unrelated containers).
- [ ] Unused project images removed (`docker images` doesn’t list your quiz image).
- [ ] `.env` and any other local secret files deleted on the NUC.
- [ ] Project‑specific API keys (OpenAI, GitHub PAT) revoked if no longer needed.
- [ ] `nuc-quiz-tunnel` deleted in Cloudflare, and DNS for `api.yourdomain.com` cleaned up.
- [ ] Cloudflared stopped (and optionally uninstalled).
- [ ] GitHub workflows referencing `self-hosted` or schedules are disabled or updated.

Once all of these are checked, your NUC and GitHub repo should be fully free of this project’s CI/CD and deployment footprint.

