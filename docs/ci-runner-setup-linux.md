# One-time setup: self-hosted GitHub Actions runner on prd-docker-01

This runs the CI pipeline directly on the Docker deploy target. Same pattern already used
for `barrycarey/TotalWellness` and `barrycarey/TrekFauna` on prd-media-01.ho.me (see that
repo's own `docs/ci-runner-setup-linux.md` for the fuller investigation history) --
self-hosted runners are scoped per-repo, so this is a separate registration in its own
directory (`~/actions-runner-redditrepostsleuth`) so it can't collide with a runner for
any other repo that ends up on this same host later.

Unlike TotalWellness/TrekFauna, there's no containerized build-image job here -- the
`deploy` job runs `docker compose build` directly using this repo's own Dockerfiles
(`docker/Dockerfile.{worker,api,monitor}`), so the runner just needs `docker` + `docker
compose` on its `PATH`, which `barry` already has.

## Step 1 - SSH in and become barry (if not already)

```bash
ssh barry@prd-docker-01.ho.me
```

The runner service will run as `barry` -- the same account that owns `/home/barry/RedditRepostSleuth`.

## Step 2 - Install the GitHub Actions runner (the one step needing sudo)

```bash
mkdir -p ~/actions-runner-redditrepostsleuth && cd ~/actions-runner-redditrepostsleuth
curl -fsSL -o runner.tar.gz \
  https://github.com/actions/runner/releases/download/v2.337.0/actions-runner-linux-x64-2.337.0.tar.gz
tar xzf runner.tar.gz
rm runner.tar.gz
```

Get a registration token (run this from anywhere you have `gh` authenticated):

```bash
gh api -X POST repos/barrycarey/RedditRepostSleuth/actions/runners/registration-token --jq .token
```

Back on prd-docker-01:

```bash
cd ~/actions-runner-redditrepostsleuth
./config.sh --url https://github.com/barrycarey/RedditRepostSleuth \
  --token <TOKEN_FROM_ABOVE> \
  --name prd-docker-01-redditrepostsleuth \
  --labels self-hosted,Linux,prd-docker-01,redditrepostsleuth \
  --work _work \
  --unattended
```

`config.sh` is non-interactive with `--unattended` -- no password needed for this part.

Now install as a systemd service -- **this is the one step needing sudo**:

```bash
sudo ./svc.sh install barry
sudo ./svc.sh start
```

## Step 3 - Verify

```bash
sudo ./svc.sh status
```

Then confirm GitHub sees it:

```bash
gh api repos/barrycarey/RedditRepostSleuth/actions/runners --jq \
  '.runners[] | {name, status, busy, labels: [.labels[].name]}'
```

Expect `status: "online"`, `busy: false`, labels including `self-hosted`, `Linux`,
`prd-docker-01`, `redditrepostsleuth`.

## Step 4 - Order matters: runner first, then merge/push

Do **not** push/merge to `master` until Step 3 shows the runner online. A push with no
matching runner leaves the job queued ("Waiting for a runner to pick up this job"), and
GitHub cancels self-hosted jobs unclaimed after 24 hours.

Once online, the first real run can be triggered manually before trusting it to an
unattended push:

```bash
gh workflow run master-deploy.yml --repo barrycarey/RedditRepostSleuth --ref master
gh run watch --repo barrycarey/RedditRepostSleuth
```

Watch `docker compose ps` / `docker compose logs -f` on the box as it comes up too --
this is a real production cutover from a stale deployment, not a routine redeploy.

## Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `deploy` job: "Permission denied" running `deploy.sh` | Shouldn't happen -- the workflow invokes `bash deploy.sh`, not `./deploy.sh` -- but if it does, check the file didn't lose its `bash` invocation | Confirm the workflow step still reads `run: bash deploy.sh --local --redeploy` |
| `deploy` job fails at the `sleuth_config.json` check | Real credentials file missing from `/home/barry/RedditRepostSleuth` | It's gitignored and never written by CI -- copy it there manually. It already existed before this pipeline was set up; confirm it wasn't accidentally moved/deleted. |
| Runs queue and never start | Runner service stopped, or the box is down | `sudo ./svc.sh status` in `~/actions-runner-redditrepostsleuth` |
| `git diff --quiet HEAD` fails deploy.sh's dirty-tree guard | Should not happen on a fresh Actions checkout -- investigate if it does, don't bypass with `--no-commit-check` | `git status` in the runner's `_work` checkout |

## Removing the runner

```bash
cd ~/actions-runner-redditrepostsleuth
sudo ./svc.sh stop
sudo ./svc.sh uninstall
./config.sh remove --token "$(gh api -X POST repos/barrycarey/RedditRepostSleuth/actions/runners/remove-token --jq .token)"
```

## Security note

Self-hosted runners execute whatever a workflow file on the triggering branch says. This
is safe here because the repository is **private** -- only you can push to `master`, and
there are no fork pull requests. The runner IS the production Docker host, so a
compromised workflow file has direct access to the running application and its data. If
this repo is ever made public, remove the self-hosted runner first.
