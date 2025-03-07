#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Display usage information
function show_usage {
    echo -e "${YELLOW}Usage:${NC} bash release.sh <version_tag>"
    echo -e "${YELLOW}Example:${NC} bash release.sh v0.3.1"
    echo ""
    echo "The version tag must follow the format 'vX.Y.Z' where X, Y, Z are numbers."
}

# Validate version tag format with proper semver regex
function validate_version_tag {
    if [[ ! "${1}" =~ ^v[0-9]+\.[0-9]+\.[0-9]+(-[a-zA-Z0-9\.]+)?$ ]]; then
        echo -e "${RED}Error:${NC} Invalid version tag format!"
        echo "The version tag must follow the format 'vX.Y.Z' or 'vX.Y.Z-suffix'"
        show_usage
        exit 1
    fi
}

# Check if we're on the main branch
function check_branch {
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$current_branch" != "main" ]]; then
        echo -e "${RED}Error:${NC} You are not on the main branch!"
        echo "Current branch: $current_branch"
        echo "Please switch to the main branch before creating a release."
        exit 1
    fi
}

# Check for uncommitted changes
function check_uncommitted_changes {
    if ! git diff-index --quiet HEAD --; then
        echo -e "${YELLOW}Warning:${NC} You have uncommitted changes."
        read -p "Do you want to continue anyway? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborting release process."
            exit 1
        fi
    fi
}

# Check if tag already exists
function check_tag_exists {
    if git tag -l | grep -q "^${1}$"; then
        echo -e "${RED}Error:${NC} Tag ${1} already exists!"
        echo "Please use a different version tag."
        exit 1
    fi
}

# Find manifest.json in a safer way
function update_manifest {
    local version_tag="$1"
    local manifest_files=$(find "$PWD" -name manifest.json -not -path "*/node_modules/*" -not -path "*/\.*")
    local manifest_count=$(echo "$manifest_files" | wc -l)

    if [[ -z "$manifest_files" ]]; then
        echo -e "${RED}Error:${NC} manifest.json not found!"
        exit 1
    elif [[ "$manifest_count" -gt 1 ]]; then
        echo -e "${YELLOW}Warning:${NC} Found multiple manifest.json files:"
        echo "$manifest_files"
        echo "Please specify which one to update:"
        select manifest_file in $manifest_files; do
            if [[ -n "$manifest_file" ]]; then
                break
            fi
        done
    else
        manifest_file="$manifest_files"
    fi

    echo -e "${GREEN}Updating version in:${NC} $manifest_file"

    # Use different sed syntax for macOS vs Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$manifest_file"
    else
        sed -i "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$manifest_file"
    fi

    echo -e "${GREEN}✓ Version updated to ${version_tag} in manifest.json${NC}"
}

# Main execution starts here

# Check if version tag is provided
if [ -z "${1}" ]; then
    echo -e "${RED}Error:${NC} You forgot to add a release tag!"
    show_usage
    exit 1
fi

VERSION_TAG="${1}"
validate_version_tag "$VERSION_TAG"
check_branch
check_uncommitted_changes
check_tag_exists "$VERSION_TAG"

echo -e "${YELLOW}Starting release process for ${VERSION_TAG}...${NC}"

# Pull latest changes
echo -e "${YELLOW}Pulling latest changes...${NC}"
if ! git pull; then
    echo -e "${RED}Error:${NC} Failed to pull latest changes."
    echo "Please fix the error, then try again."
    exit 1
fi
echo -e "${GREEN}✓ Latest changes pulled${NC}"

# Update manifest.json
update_manifest "$VERSION_TAG"

# Stage files
echo -e "${YELLOW}Staging changes...${NC}"
git add -A
echo -e "${GREEN}✓ Changes staged${NC}"

# Show summary of changes
echo -e "${YELLOW}Summary of changes to be committed:${NC}"
git status --short

# Confirm commit
echo
read -p "Do you want to proceed with the commit and push? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborting release process."
    exit 1
fi

# Commit changes
echo -e "${YELLOW}Committing changes...${NC}"
git commit -m "Release ${VERSION_TAG}"
echo -e "${GREEN}✓ Changes committed${NC}"

# Push to main
echo -e "${YELLOW}Pushing to main branch...${NC}"
git push origin main
echo -e "${GREEN}✓ Changes pushed to main${NC}"

# Create and push tag
echo -e "${YELLOW}Creating and pushing tag ${VERSION_TAG}...${NC}"
git tag "${VERSION_TAG}"
git push origin "${VERSION_TAG}"
echo -e "${GREEN}✓ Tag ${VERSION_TAG} created and pushed${NC}"

echo -e "${GREEN}Release ${VERSION_TAG} successfully completed!${NC}"
