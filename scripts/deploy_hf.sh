#!/usr/bin/env bash
# Deploy the current commit to a Hugging Face Space (Docker).
# One-time:  git remote add space https://huggingface.co/spaces/<user>/<space-name>
# Each time: bash scripts/deploy_hf.sh
set -euo pipefail
branch=$(git rev-parse --abbrev-ref HEAD)
git diff --quiet && git diff --cached --quiet || { echo "Commit your changes first."; exit 1; }
git checkout -B hf-deploy
cp deploy/hf_README.md README.md
git add README.md && git commit -m "deploy: Hugging Face Space README" || true
git push space hf-deploy:main --force
git checkout "$branch"
git branch -D hf-deploy
echo "Deployed. Watch the build in the Space's Logs tab."
