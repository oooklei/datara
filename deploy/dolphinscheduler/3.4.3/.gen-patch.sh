#!/bin/bash
set -e
WORK=/lei/dolphinscheduler/dolphinscheduler-3.4.3
PRISTINE=/lei/dolphinscheduler/ds-pristine/dolphinscheduler-3.4.3
rm -rf /tmp/patchgen
mkdir -p /tmp/patchgen
cd /tmp/patchgen
git init -q .
git config user.email a@b.c
git config user.name a
cp -a "$PRISTINE/." .
git add -A >/dev/null
git commit -qm base
while IFS= read -r f; do
  mkdir -p "$(dirname "$f")"
  cp "$WORK/$f" "$f"
done < /tmp/patchfiles.txt
git add -A
git diff --cached > /tmp/datara-integration.clean.patch
echo "--- stat ---"
git diff --cached --stat | tail -5
echo "--- lines ---"
wc -l /tmp/datara-integration.clean.patch
echo "--- files touched ---"
git diff --cached --name-only | wc -l
