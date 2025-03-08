#!/bin/bash
set -e  # Exit immediately if a command exits with a non-zero status

# Colors for better readability
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Integration naming constants
MAIN_NAME="OVMS Home Assistant"
SHORT_NAME="OVMS"
FULL_NAME="Open Vehicle Monitoring System HA"
REPO_NAME="ovms-home-assistant"  # Current repository name

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    echo -e "${RED}Error:${NC} GitHub CLI (gh) is not installed."
    echo "Please install it from https://cli.github.com/ and authenticate."
    exit 1
fi

# Check if jq is installed
if ! command -v jq &> /dev/null; then
    echo -e "${RED}Error:${NC} jq is not installed."
    echo "Please install it using your package manager."
    exit 1
fi

# Display usage information
function show_usage {
    echo -e "${YELLOW}Usage:${NC} bash release.sh <version_tag> [options]"
    echo -e "${YELLOW}Example:${NC} bash release.sh v0.3.1"
    echo ""
    echo "Options:"
    echo "  --pr-only     Create a PR for the release without pushing tags"
    echo "  --help        Show this help message"
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

# Generate release notes based on commits and PRs since the last release
function generate_release_notes {
    local version_tag="$1"
    local last_tag=$(git describe --abbrev=0 --tags 2>/dev/null || echo "")
    
    # Status messages to stderr so they don't get captured in the variable assignment
    echo -e "${YELLOW}Generating release notes...${NC}" >&2
    
    # Create a temporary file for release notes
    local release_notes_file=$(mktemp)
    
    # Add header to release notes with main name
    echo "# ${MAIN_NAME} ${version_tag}" > "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Add release date
    echo "Released on $(date +'%Y-%m-%d')" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Add section for merged PRs
    echo "## What's Changed" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    if [[ -n "$last_tag" ]]; then
        # Get merged PRs since last tag using GitHub CLI
        echo -e "${BLUE}Fetching merged PRs since ${last_tag}...${NC}" >&2
        
        # Use GitHub CLI to get merged PRs
        pr_list=$(gh pr list --state merged --base main --json number,title,author,mergedAt,url --limit 100)
        
        if [[ -n "$pr_list" ]]; then
            # Filter PRs merged after the last tag date
            last_tag_date=$(git log -1 --format=%ai "$last_tag" 2>/dev/null)
            
            if [[ -n "$last_tag_date" ]]; then
                # Format PRs into Markdown list
                echo "$pr_list" | jq -r --arg date "$last_tag_date" '.[] | 
                    select(.mergedAt > $date) | 
                    "* " + .title + " (#" + (.number|tostring) + ") @" + .author.login' >> "$release_notes_file"
            else
                # If we can't get the last tag date, include all PRs
                echo "$pr_list" | jq -r '.[] | 
                    "* " + .title + " (#" + (.number|tostring) + ") @" + .author.login' >> "$release_notes_file"
            fi
        else
            echo "* No PRs merged since last release" >> "$release_notes_file"
        fi
    else
        # If there's no previous tag, get all commits
        echo -e "${BLUE}No previous tag found. Including all commits...${NC}" >&2
        
        # Get commits
        git log --pretty=format:"* %s (%h)" --no-merges | head -n 10 >> "$release_notes_file"
    fi
    
    echo "" >> "$release_notes_file"
    echo "## Full Changelog" >> "$release_notes_file"
    
    if [[ -n "$last_tag" ]]; then
        echo "[$last_tag...${version_tag}](https://github.com/enoch85/${REPO_NAME}/compare/${last_tag}...${version_tag})" >> "$release_notes_file"
    else
        echo "[${version_tag}](https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag})" >> "$release_notes_file"
    fi
    
    echo -e "${GREEN}✓ Release notes generated${NC}" >&2
    
    # Only output the filename, which will be captured by the variable assignment
    echo "$release_notes_file"
}

# Create a PR for the release
function create_release_pr {
    local version_tag="$1"
    local branch_name="release/${version_tag}"
    local release_notes_file="$2"
    
    echo -e "${YELLOW}Creating release branch ${branch_name}...${NC}"
    
    # Create branch
    git checkout -b "$branch_name"
    
    # Commit changes
    git add -A
    git commit -m "Release ${version_tag}"
    
    # Push branch
    git push -u origin "$branch_name"
    
    echo -e "${GREEN}✓ Release branch pushed${NC}"
    
    # Create PR using GitHub CLI
    echo -e "${YELLOW}Creating pull request...${NC}"
    
    # Use the release notes as PR description
    pr_url=$(gh pr create --base main --head "$branch_name" --title "${MAIN_NAME} ${version_tag}" --body-file "$release_notes_file")
    
    echo -e "${GREEN}✓ Release PR created: ${pr_url}${NC}"
    
    # Cleanup
    git checkout main
    
    echo -e "${BLUE}Instructions:${NC}"
    echo "1. Review the PR: $pr_url"
    echo "2. Make any necessary changes to the release branch"
    echo "3. Once approved, merge the PR"
    echo "4. Run this script again without --pr-only to push the tag and create a release"
}

# Create a GitHub release notice (modified to skip creating actual release)
function create_github_release {
    local version_tag="$1"
    local release_notes_file="$2"
    
    echo -e "${YELLOW}Skipping GitHub release creation - will be handled by GitHub Actions...${NC}"
    echo -e "${BLUE}Release notes that will be used for GitHub Actions:${NC}"
    cat "$release_notes_file"
    echo
    echo -e "${GREEN}✓ GitHub release will be created automatically by GitHub Actions when tag is pushed${NC}"
    echo -e "${BLUE}If you want to review the release after it's created, visit:${NC}"
    echo "https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag}"
}

# Main execution starts here

# Parse arguments
PR_ONLY=false

while [[ "$#" -gt 0 ]]; do
    case $1 in
        --pr-only) PR_ONLY=true; shift ;;
        --help) show_usage; exit 0 ;;
        -h) show_usage; exit 0 ;;
        -*) echo "Unknown option: $1"; show_usage; exit 1 ;;
        *) VERSION_TAG="$1"; shift ;;
    esac
done

# Check if version tag is provided
if [ -z "${VERSION_TAG}" ]; then
    echo -e "${RED}Error:${NC} You forgot to add a release tag!"
    show_usage
    exit 1
fi

validate_version_tag "$VERSION_TAG"
check_branch
check_uncommitted_changes
check_tag_exists "$VERSION_TAG"

echo -e "${YELLOW}Starting release process for ${MAIN_NAME} ${VERSION_TAG}...${NC}"

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

# Generate release notes - Only capture the file path, not the status messages
RELEASE_NOTES_FILE=$(generate_release_notes "$VERSION_TAG")

# Create either a PR or a full release
if [[ "$PR_ONLY" == true ]]; then
    create_release_pr "$VERSION_TAG" "$RELEASE_NOTES_FILE"
else
    # Stage files
    echo -e "${YELLOW}Staging changes...${NC}"
    git add -A
    echo -e "${GREEN}✓ Changes staged${NC}"

    # Show summary of changes
    echo -e "${YELLOW}Summary of changes to be committed:${NC}"
    git status --short

    # Display release notes
    echo -e "${YELLOW}Release Notes:${NC}"
    cat "$RELEASE_NOTES_FILE"
    echo

    # Confirm commit
    read -p "Do you want to proceed with the commit, push, and release? (y/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Aborting release process."
        exit 1
    fi

    # Commit changes
    echo -e "${YELLOW}Committing changes...${NC}"
    git commit -m "Release ${VERSION_TAG} of ${MAIN_NAME}"
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

    # Create GitHub release (now just displays a notice)
    create_github_release "$VERSION_TAG" "$RELEASE_NOTES_FILE"

    echo -e "${GREEN}${MAIN_NAME} ${VERSION_TAG} successfully prepared!${NC}"
    echo -e "${BLUE}The GitHub Actions workflow will now create the actual release.${NC}"
    echo -e "${BLUE}You can monitor the process at:${NC} https://github.com/enoch85/${REPO_NAME}/actions"
fi

# Clean up temporary file
if [[ -f "$RELEASE_NOTES_FILE" ]]; then
    rm "$RELEASE_NOTES_FILE"
fi
