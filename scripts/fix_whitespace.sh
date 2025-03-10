#!/bin/bash

# Pull latest changes
git pull

# Fix whitespace
cd "$(pwd)/custom_components/ovms"
find . -name "*.py" -exec sed -i 's/[ \t]*$//' {} \;

# Commit and push!
git commit -a -s -m "fix whitespace"
git push origin fix-lint

