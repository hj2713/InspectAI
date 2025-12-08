#!/bin/bash

# Usage: ./run_cli.sh <URL>
if [ -z "$1" ]; then
  echo "Error: Please provide a PR URL."
  echo "Usage: ./run_cli.sh https://github.com/owner/repo/pull/123"
  exit 1
fi

echo "🚀 Triggering Manual Inspection..."
python3 src/cli/manual_trigger.py --url "$1" --dry-run