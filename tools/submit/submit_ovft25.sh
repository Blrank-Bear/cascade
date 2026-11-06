#!/bin/bash
# Human-run Lane A submission of the ovft25 package (wallet NM / hotkey hk2).
# Run from WSL Ubuntu:  bash /mnt/d/CODE/Bittensor/cascade/cascade/tools/submit/submit_ovft25.sh
# Gates, in order (any failure stops before anything is sent or paid):
#   1. live launch_preflight must not be "blocked"
#   2. package files must match the reviewed hashes
#   3. `cascade verify --live` must pass
#   4. preflight (informational; its 30 s quick check times out on this PC, which submit does not use)
#   5. Lium key read silently, explicit "SUBMIT" confirmation, then a funded `cascade submit`
# The key lives only in this process's environment; it is never echoed or written.
set -u
ROOT=/mnt/d/CODE/Bittensor/cascade/cascade
C=$ROOT/.claude-work/venv/bin/cascade
PKG=$ROOT/submission/ovft25/generator
INTAKE=https://submissions.cascadesub.net
WALLET=NM
HOTKEY=hk2
HK=5HEYumdHFGjeSTgaH2JiWkhTapwXiqZDLtHeDgtGptfGXvWa   # hk2 public address, uid 166 on netuid 91
LOG=$ROOT/submission/ovft25/logs/submit_$(date -u +%Y%m%dT%H%M%SZ)
EXPECT="885ad5fe config.json
48197f5c generator.py
c77f45b6 requirements.txt
cd254841 v2_lcpr.json
41b010a8 v2_ovl.json"

cd $ROOT/upstream || exit 1
mkdir -p "$(dirname "$LOG")"

echo "[1/5] network launch status"
STATE=$(curl -s -m 30 https://s3.hippius.com/cascade-manifests/status/v2.json \
  | python3 -c "import sys,json; d=json.load(sys.stdin)['launch_preflight']; print(d['state']); print(d.get('reason',''), file=sys.stderr)")
echo "      state: $STATE"
if [ "$STATE" = "blocked" ] || [ -z "$STATE" ]; then
  echo "STOP: Lane A launches are still blocked by the network. Nothing was sent. Try again later."; exit 2
fi

echo "[2/5] package integrity"
rm -rf "$PKG/__pycache__"
GOT=$(cd "$PKG" && for f in config.json generator.py requirements.txt v2_lcpr.json v2_ovl.json; do echo "$(sha256sum $f | cut -c1-8) $f"; done)
EXTRA=$(cd "$PKG" && ls -A | grep -vxE 'config.json|generator.py|requirements.txt|v2_lcpr.json|v2_ovl.json')
if [ "$GOT" != "$EXPECT" ] || [ -n "$EXTRA" ]; then
  echo "STOP: package differs from the reviewed build:"; echo "$GOT"; echo "extra: $EXTRA"; exit 3
fi
echo "      ok (5 files, hashes match the reviewed build)"

echo "[3/5] verify against the live contract (takes a few minutes)"
$C verify "$PKG" --live --json > "$LOG.verify_live.json" 2>&1
if ! grep -q '"ok": true, "schema"' "$LOG.verify_live.json"; then
  echo "STOP: live verify failed. Details: $LOG.verify_live.json"; tail -c 800 "$LOG.verify_live.json"; echo; exit 4
fi
echo "      ok"

echo "[4/5] preflight (informational)"
$C preflight "$PKG" --lane a --hotkey $HK --max-price 40 --max-spend 150 --json > "$LOG.preflight.json" 2>&1
python3 - "$LOG.preflight.json" <<'PY'
import json, sys
s = open(sys.argv[1]).read(); i = s.find('{"command"')
d = json.loads(s[i:]) if i >= 0 else {}
for c in d.get("data", {}).get("checks", []):
    print("      %-8s %s" % (c.get("state"), c.get("check")))
PY
rm -rf "$PKG/__pycache__"

echo "[5/5] submit + fund"
echo "      Make sure your Lium key has a spending budget set on lium.io (e.g. \$150)."
printf "      Paste your LIUM_API_KEY (hidden) and press Enter: "
read -rs LIUM_API_KEY; echo
[ -n "$LIUM_API_KEY" ] || { echo "STOP: empty key."; exit 5; }
export LIUM_API_KEY
printf "      Type SUBMIT to send ovft25 from %s/%s and rent its training pod: " $WALLET $HOTKEY
read -r OK
[ "$OK" = "SUBMIT" ] || { unset LIUM_API_KEY; echo "STOP: not confirmed. Nothing was sent."; exit 6; }

$C submit "$PKG" $INTAKE --wallet-name $WALLET --wallet-hotkey $HOTKEY --label ovft25 --yes 2>&1 | tee "$LOG.submit.txt"
RC=${PIPESTATUS[0]}
unset LIUM_API_KEY
echo "submit exit code: $RC   (log: $LOG.submit.txt)"
[ $RC -eq 0 ] || exit $RC

echo
echo "Submitted. Track it with:"
echo "  $C reveal-status $HK --watch"
echo "  $C queue --intake $INTAKE --hotkey $HK"
