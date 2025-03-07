#/bin/bash

if [ -z "${1}" ]
then
    echo "You forgot to add a release tag."
    echo "Example: bash release.sh [v0.3.1]"
    exit 1
fi

# Pull latest changes
if ! git pull
then
    echo "Please fix the error, then try again."
    exit 1
fi

# Change version in manifest.json
ovms_manifest_file="$(find "$PWD" -name manifest.json)"
if [ -f "$ovms_manifest_file" ]
then
    sed "s|\"version\":.*|\"version\": \"${1}\"|g" "$ovms_manifest_file"
else
    echo "manifest.json not found!"
    exit 1
fi

# Add missing files
git add -A

# Commit change
git commit -a -m "${1}"

# Create new release tag
git tag "${1}"

# Push to origin
git push origin "${1}"
