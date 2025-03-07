#/bin/bash

if [ -z "${1}" ]
then
    echo "You forgot to add a release tag!"
    echo "Example: 'bash release.sh v0.3.1'"
    exit 1
elif ! echo "${1}" | grep "v"
then
    echo "You forgot to add 'v' in the release tag!"
    echo "Example: 'bash release.sh v0.3.1'"
    exit 1
fi

# Pull latest changes
if ! git pull
then
    echo "Please fix the error, then try again."
    exit 1
fi

# Add missing files
git add -A

# Change version in manifest.json
ovms_manifest_file="$(find "$PWD" -name manifest.json)"
if [ -f "$ovms_manifest_file" ]
then
    sed -i "s|\"version\":.*|\"version\": \"${1}\"|g" "$ovms_manifest_file"
else
    echo "manifest.json not found!"
    exit 1
fi

# Commit change
git commit -a -m "${1}"

# Push change to main
git push origin main

# Create new release tag for the release workflow to work
git tag "${1}"

# Push to origin
git push origin "${1}"
