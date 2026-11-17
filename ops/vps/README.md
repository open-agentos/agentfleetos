# ops/vps: the engine host (owner only)

1. In Hetzner, create an Ubuntu 24.04 or 26.04 server with your SSH key, and point the Desk's DNS name at it.
2. Copy this folder over and run: `DESK_HOST=<name> bash provision.sh` as root.
3. Put the secrets in `/etc/agentfleetos/secrets.env` (root:swarm, 0640) yourself: `ANTHROPIC_API_KEY`, `WEBHOOK_SECRET`, `GH_TOKEN` and each App's key. No agent or session ever sees this file.
   - `GH_TOKEN` is what the watcher reads GitHub with. Use a fine-grained token with read-only access to the repo (Contents, Issues, Pull requests, Metadata) and the org Project. Nothing on the host writes with it.
4. In each role App's settings, set the webhook URL to `https://<name>/webhooks/github` with the same `WEBHOOK_SECRET`.

## The services (#660)

`systemd/` has five units. All run as the `swarm` user from a checkout at `/home/swarm/agentfleetos`, with state in `/home/swarm/.agentfleetos/launcher/swarm.db`. Each service sets `PRODUCTSWARM_HOME=/home/swarm/.agentfleetos`. The variable keeps its old name (GOV-0048), and `provision.sh` links `~/.productswarm` to the state folder, so commands you run by hand as `swarm` find the same state.

| Unit | Runs | Reads |
|---|---|---|
| `agentfleetos-webhooks.service` | `swarm webhooks` on 127.0.0.1:8081, behind Caddy | `webhooks.env`: only `WEBHOOK_SECRET` |
| `agentfleetos-watch.service` | `swarm watch --serve --dry-run`: a check on each webhook nudge (at most every 30 s) and every `interval_minutes` | `secrets.env` |
| `agentfleetos-desk.service` | `swarm desk` on 127.0.0.1:8080, behind Caddy (#664) | `desk.env`: only the read-only `GH_TOKEN` |
| `agentfleetos-backup.service` and `.timer` | `swarm backup` nightly at 03:30 UTC | nothing secret |

The watcher runs with `--dry-run` until #661: starting role sessions here needs #661's containers. Take `--dry-run` off then. Until then the checkout doesn't update itself, so pull it by hand after merges.

The Desk's `--repo` must be the current slug. GitHub redirects most API calls after a rename, but not search, so an old slug stops the Desk publishing.

Install, as root:

```bash
sudo -u swarm git clone https://github.com/open-agentos/agentfleetos /home/swarm/agentfleetos
grep '^WEBHOOK_SECRET=' /etc/agentfleetos/secrets.env > /etc/agentfleetos/webhooks.env
grep -E '^(GH_TOKEN|GITHUB_TOKEN)=' /etc/agentfleetos/secrets.env > /etc/agentfleetos/desk.env
chown root:swarm /etc/agentfleetos/webhooks.env /etc/agentfleetos/desk.env && chmod 640 /etc/agentfleetos/webhooks.env /etc/agentfleetos/desk.env
cp /root/vps/systemd/agentfleetos-* /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now agentfleetos-webhooks agentfleetos-watch agentfleetos-desk agentfleetos-backup.timer
```

Check: `systemctl status agentfleetos-webhooks agentfleetos-watch agentfleetos-desk` and `journalctl -u agentfleetos-watch -f`. To stop everything starting work, add `swarm:halt` to the report issue (#249); only your label counts.

The units, paths and secrets folder were called `productswarm-*`, `/home/swarm/productswarm`, `/home/swarm/.productswarm` and `/etc/productswarm` until 2026-11-17 (GOV-0048).
