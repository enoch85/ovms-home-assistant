#!/bin/bash

# Check if ${1}" is empty
if [ -z "${1}" ]
then
    echo "You forgot to choose which branch to push to!"
    echo "Example: 'bash fix_whitespace.sh devbranch'."
    exit 1
fi

# Pull latest changes
git pull

# Fix whitespace
find "../custom_components/ovms" -name "*.py" -exec sed -i 's/[ \t]*$//' {} \;

# Commit and push!
git commit -a -s -m "fix whitespace"
git push origin "${1}"

