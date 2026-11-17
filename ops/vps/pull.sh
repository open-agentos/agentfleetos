#!/usr/bin/env bash
# ops/vps/pull.sh: keep the engine host's checkout on main (run by agentfleetos-pull.timer).
# Installed as root to /usr/local/sbin/agentfleetos-pull, not run from the checkout: anything
# merged to main may change the checkout, so nothing in it runs as root.
# Pulls as the swarm user, fast-forward only. If launcher/ changed, restarts the services that
# hold it in memory. dashboard/ needs nothing: the Desk runs generate.py afresh on each build.
# A change under ops/ is logged, never installed: copying units and scripts stays the owner's.
set -euo pipefail

CHECKOUT=/home/swarm/agentfleetos
SERVICES=(agentfleetos-webhooks agentfleetos-watch agentfleetos-desk)
git_swarm() { runuser -u swarm -- env HOME=/home/swarm git -C "$CHECKOUT" "$@"; }

before=$(git_swarm rev-parse HEAD)
if [ "$(git_swarm rev-parse --abbrev-ref HEAD)" != main ]; then
  echo "checkout is not on main; not pulling" >&2
  exit 1
fi
git_swarm pull --ff-only --quiet origin main
after=$(git_swarm rev-parse HEAD)
[ "$before" = "$after" ] && exit 0

changed=$(git_swarm diff --name-only "$before" "$after")
echo "pulled ${before:0:7}..${after:0:7} ($(echo "$changed" | wc -l) files)"
if echo "$changed" | grep -q '^launcher/'; then
  echo "launcher/ changed: restarting ${SERVICES[*]}"
  systemctl try-restart "${SERVICES[@]}"
fi
if echo "$changed" | grep -q '^ops/'; then
  echo "ops/ changed; install it by hand if needed:" $(echo "$changed" | grep '^ops/')
fi
