#!/bin/bash
# More robust release script for OVMS Home Assistant

# Don't use set -e as it causes script to exit on any error
# Instead we'll handle errors explicitly

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

# Debug mode - set to true to enable more detailed output
DEBUG=true

# Debug function
function debug_log {
    if [[ "$DEBUG" == "true" ]]; then
        echo -e "${BLUE}DEBUG:${NC} $1" >&2
    fi
}

# Error function
function error_log {
    echo -e "${RED}ERROR:${NC} $1" >&2
}

# Info function
function info_log {
    echo -e "${YELLOW}INFO:${NC} $1" >&2
}

# Success function 
function success_log {
    echo -e "${GREEN}SUCCESS:${NC} $1" >&2
}

# Check if GitHub CLI is installed
if ! command -v gh &> /dev/null; then
    error_log "GitHub CLI (gh) is not installed."
    echo "Please install it from https://cli.github.com/ and authenticate."
    exit 1
fi

# Check GitHub CLI authentication
debug_log "Checking GitHub CLI authentication..."
if ! gh auth status &> /dev/null; then
    error_log "GitHub CLI is not authenticated. Please run 'gh auth login' first."
    exit 1
fi

# Check if jq is installed - warn but don't exit if missing
if ! command -v jq &> /dev/null; then
    info_log "jq is not installed. Some features may not work correctly."
    info_log "Consider installing jq for better release note generation."
    HAS_JQ=false
else
    HAS_JQ=true
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
        error_log "Invalid version tag format!"
        echo "The version tag must follow the format 'vX.Y.Z' or 'vX.Y.Z-suffix'"
        show_usage
        exit 1
    fi
}

# Check if we're on the main branch
function check_branch {
    local current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$current_branch" != "main" ]]; then
        error_log "You are not on the main branch!"
        echo "Current branch: $current_branch"
        echo "Please switch to the main branch before creating a release."
        exit 1
    fi
}

# Check for uncommitted changes
function check_uncommitted_changes {
    if ! git diff-index --quiet HEAD --; then
        info_log "You have uncommitted changes."
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
        error_log "Tag ${1} already exists!"
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
        error_log "manifest.json not found!"
        exit 1
    elif [[ "$manifest_count" -gt 1 ]]; then
        info_log "Found multiple manifest.json files:"
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

    debug_log "Updating version in: $manifest_file"

    # Check if version is already updated
    local current_version=$(grep -o '"version": *"[^"]*"' "$manifest_file" | cut -d'"' -f4)
    if [[ "$current_version" == "$version_tag" ]]; then
        info_log "Version is already set to ${version_tag} in manifest.json"
        return 0
    fi

    # Use different sed syntax for macOS vs Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$manifest_file"
    else
        sed -i "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$manifest_file"
    fi

    success_log "Version updated to ${version_tag} in manifest.json"
    return 1  # Return non-zero to indicate changes were made
}

# Check if any changes were made to files
function check_for_changes {
    if git diff --quiet; then
        return 1  # No changes
    else
        return 0  # Changes detected
    fi
}

# Generate simple release notes when GitHub API fails
function generate_simple_release_notes {
    local version_tag="$1"
    local last_tag=$(git describe --abbrev=0 --tags 2>/dev/null || echo "")
    
    # Create a temporary file for release notes
    local release_notes_file=$(mktemp)
    
    # Add header to release notes with main name
    echo "# ${MAIN_NAME} ${version_tag}" > "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Add release date
    echo "Released on $(date +'%Y-%m-%d')" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Add section for changes
    echo "## What's Changed" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Just list recent commits
    if [[ -n "$last_tag" ]]; then
        echo "Recent changes since $last_tag:" >> "$release_notes_file"
        git log --pretty=format:"* %s (%h)" --no-merges "$last_tag..HEAD" | head -n 10 >> "$release_notes_file"
    else
        echo "Recent changes:" >> "$release_notes_file"
        git log --pretty=format:"* %s (%h)" --no-merges -n 10 >> "$release_notes_file"
    fi
    
    echo "" >> "$release_notes_file"
    echo "## Full Changelog" >> "$release_notes_file"
    
    if [[ -n "$last_tag" ]]; then
        echo "[$last_tag...${version_tag}](https://github.com/enoch85/${REPO_NAME}/compare/${last_tag}...${version_tag})" >> "$release_notes_file"
    else
        echo "[${version_tag}](https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag})" >> "$release_notes_file"
    fi
    
    debug_log "Simple release notes generated at $release_notes_file"
    echo "$release_notes_file"
}

# Generate release notes based on commits and PRs since the last release
function generate_release_notes {
    local version_tag="$1"
    
    # Try to use GitHub CLI, but fall back to simple release notes if it fails
    info_log "Generating release notes..."
    
    # Create simple release notes by default
    local simple_notes_file=$(generate_simple_release_notes "$version_tag")
    
    debug_log "Simple release notes created at $simple_notes_file"
    
    # Try to get more detailed release notes with GitHub CLI if possible
    if [[ "$HAS_JQ" == "true" ]]; then
        debug_log "Attempting to generate more detailed release notes using GitHub CLI..."
        
        local last_tag=$(git describe --abbrev=0 --tags 2>/dev/null || echo "")
        local detailed_notes_file=$(mktemp)
        
        # Copy the simple notes header
        head -n 5 "$simple_notes_file" > "$detailed_notes_file"
        
        # Add section for merged PRs
        echo "## What's Changed" >> "$detailed_notes_file"
        echo "" >> "$detailed_notes_file"
        
        # Check if GitHub CLI can access PR data
        local pr_data_ok=false
        
        if gh pr list --limit 1 &>/dev/null; then
            debug_log "GitHub CLI can access PR data"
            pr_data_ok=true
        else
            debug_log "GitHub CLI cannot access PR data, using simple notes"
            pr_data_ok=false
        fi
        
        if [[ "$pr_data_ok" == "true" && -n "$last_tag" ]]; then
            debug_log "Fetching PRs since $last_tag"
            
            # Try to get PR data, but don't fail if it doesn't work
            if pr_list=$(gh pr list --state merged --base main --json number,title,author,mergedAt,url --limit 10 2>/dev/null); then
                if echo "$pr_list" | jq empty &>/dev/null && [[ "$pr_list" != "[]" && -n "$pr_list" ]]; then
                    debug_log "Got valid PR list from GitHub CLI"
                    
                    # Format PRs into markdown
                    if pr_formatted=$(echo "$pr_list" | jq -r '.[] | "* " + .title + " (#" + (.number|tostring) + ")"'); then
                        debug_log "Formatted PR list successfully"
                        echo "$pr_formatted" >> "$detailed_notes_file"
                        
                        # Add the footer
                        tail -n 3 "$simple_notes_file" >> "$detailed_notes_file"
                        
                        # Use the detailed notes
                        debug_log "Using detailed release notes"
                        rm "$simple_notes_file"
                        echo "$detailed_notes_file"
                        return
                    else
                        debug_log "Failed to format PR list, using simple notes"
                    fi
                else
                    debug_log "Invalid or empty PR list, using simple notes"
                fi
            else
                debug_log "Failed to get PR list, using simple notes"
            fi
        else
            debug_log "No last tag or no PR data access, using simple notes"
        fi
        
        # If we get here, something went wrong with detailed notes
        rm "$detailed_notes_file"
    fi
    
    # Return the simple notes if detailed ones weren't generated
    debug_log "Using simple release notes as fallback"
    echo "$simple_notes_file"
}

# Create a PR for the release
function create_release_pr {
    local version_tag="$1"
    local branch_name="release/${version_tag}"
    local release_notes_file="$2"
    
    info_log "Creating release branch ${branch_name}..."
    
    # Create branch
    if ! git checkout -b "$branch_name"; then
        error_log "Failed to create branch $branch_name"
        return 1
    fi
    
    # Commit changes
    debug_log "Adding changes to git"
    if ! git add -A; then
        error_log "Failed to add changes to git"
        return 1
    fi
    
    debug_log "Committing changes"
    if ! git commit -m "Release ${version_tag}"; then
        error_log "Failed to commit changes"
        return 1
    fi
    
    # Push branch
    debug_log "Pushing branch to GitHub"
    if ! git push -u origin "$branch_name"; then
        error_log "Failed to push branch to GitHub"
        return 1
    fi
    
    success_log "Release branch pushed"
    
    # Create PR using GitHub CLI
    info_log "Creating pull request..."
    
    # Use the release notes as PR description
    if pr_url=$(gh pr create --base main --head "$branch_name" --title "${MAIN_NAME} ${version_tag}" --body-file "$release_notes_file"); then
        success_log "Release PR created: ${pr_url}"
    else
        error_log "Failed to create PR automatically. Please create it manually."
        echo "Branch: $branch_name"
        echo "Base: main"
        echo "Title: ${MAIN_NAME} ${version_tag}"
        return 1
    fi
    
    # Cleanup
    debug_log "Switching back to main branch"
    git checkout main
    
    echo -e "${BLUE}Instructions:${NC}"
    echo "1. Review the PR: $pr_url"
    echo "2. Make any necessary changes to the release branch"
    echo "3. Once approved, merge the PR"
    echo "4. Run this script again without --pr-only to push the tag and create a release"
    
    return 0
}

# Create a GitHub release notice (modified to skip creating actual release)
function create_github_release {
    local version_tag="$1"
    local release_notes_file="$2"
    
    info_log "Skipping GitHub release creation - will be handled by GitHub Actions..."
    echo -e "${BLUE}Release notes that will be used for GitHub Actions:${NC}"
    cat "$release_notes_file"
    echo
    success_log "GitHub release will be created automatically by GitHub Actions when tag is pushed"
    echo -e "${BLUE}If you want to review the release after it's created, visit:${NC}"
    echo "https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag}"
}

# Creates and pushes a tag
function create_and_push_tag {
    local version_tag="$1"
    
    info_log "Creating and pushing tag ${version_tag}..."
    if ! git tag "${version_tag}"; then
        error_log "Failed to create tag ${version_tag}"
        return 1
    fi
    
    if ! git push origin "${version_tag}"; then
        error_log "Failed to push tag ${version_tag}"
        return 1
    fi
    
    success_log "Tag ${version_tag} created and pushed"
    return 0
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
    error_log "You forgot to add a release tag!"
    show_usage
    exit 1
fi

validate_version_tag "$VERSION_TAG"
check_branch
check_uncommitted_changes
check_tag_exists "$VERSION_TAG"

info_log "Starting release process for ${MAIN_NAME} ${VERSION_TAG}..."

# Pull latest changes
info_log "Pulling latest changes..."
if ! git pull --rebase; then
    error_log "Failed to pull latest changes."
    echo "Please fix the error, then try again."
    exit 1
fi
success_log "Latest changes pulled"

# Update manifest.json - returns 0 if already updated, 1 if changes were made
update_manifest "$VERSION_TAG"
changes_made=$?
debug_log "Manifest update result: $changes_made (1=changes made, 0=no changes)"

# Generate release notes
debug_log "Generating release notes..."
RELEASE_NOTES_FILE=$(generate_release_notes "$VERSION_TAG")
debug_log "Release notes generated at $RELEASE_NOTES_FILE"

# Create either a PR or a full release
if [[ "$PR_ONLY" == true ]]; then
    info_log "Creating PR only (no tag push)..."
    
    if ! create_release_pr "$VERSION_TAG" "$RELEASE_NOTES_FILE"; then
        error_log "Failed to create PR. Please check the errors above."
        exit 1
    fi
else
    # Check if there are any changes to commit
    if [[ "$changes_made" -eq 1 ]] || check_for_changes; then
        # Stage files
        info_log "Staging changes..."
        git add -A
        success_log "Changes staged"

        # Show summary of changes
        info_log "Summary of changes to be committed:"
        git status --short

        # Display release notes
        info_log "Release Notes:"
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
        info_log "Committing changes..."
        if ! git commit -m "Release ${VERSION_TAG} of ${MAIN_NAME}"; then
            error_log "Failed to commit changes"
            exit 1
        fi
        success_log "Changes committed"

        # Push to main
        info_log "Pushing to main branch..."
        if ! git push origin main; then
            error_log "Failed to push changes to main"
            exit 1
        fi
        success_log "Changes pushed to main"

        # Create and push tag
        if ! create_and_push_tag "$VERSION_TAG"; then
            error_log "Failed to create and push tag"
            exit 1
        fi
    else
        info_log "No changes to commit. Manifest.json already has version ${VERSION_TAG}."
        
        # Display release notes
        info_log "Release Notes:"
        cat "$RELEASE_NOTES_FILE"
        echo
        
        # Confirm tag creation
        read -p "Do you want to create and push the tag ${VERSION_TAG}? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Aborting release process."
            exit 1
        fi
        
        # Create and push tag
        if ! create_and_push_tag "$VERSION_TAG"; then
            error_log "Failed to create and push tag"
            exit 1
        fi
    fi

    # Create GitHub release (now just displays a notice)
    create_github_release "$VERSION_TAG" "$RELEASE_NOTES_FILE"

    success_log "${MAIN_NAME} ${VERSION_TAG} successfully prepared!"
    echo -e "${BLUE}The GitHub Actions workflow will now create the actual release.${NC}"
    echo -e "${BLUE}You can monitor the process at:${NC} https://github.com/enoch85/${REPO_NAME}/actions"
fi

# Clean up temporary file
if [[ -f "$RELEASE_NOTES_FILE" ]]; then
    debug_log "Cleaning up temporary release notes file"
    rm "$RELEASE_NOTES_FILE"
fi

success_log "Release script completed successfully."
