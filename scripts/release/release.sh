#!/bin/bash
# OVMS Home Assistant integration release script

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
REPO_NAME="ovms-home-assistant"
INTEGRATION_PATH="custom_components/ovms"
MANIFEST_PATH="${INTEGRATION_PATH}/manifest.json"

# Release flags
IS_BETA=false

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
function check_github_cli {
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
}

# Check if jq is installed - warn but don't exit if missing
function check_jq {
    if ! command -v jq &> /dev/null; then
        info_log "jq is not installed. Some features may not work correctly."
        info_log "Consider installing jq for better release note generation."
        return 1
    fi
    return 0
}

# Display usage information
function show_usage {
    echo -e "${YELLOW}Usage:${NC} bash release.sh <version_tag> [options]"
    echo -e "${YELLOW}Example:${NC} bash release.sh v0.3.1"
    echo -e "${YELLOW}Example (beta):${NC} bash release.sh v0.3.1-beta"
    echo ""
    echo "Options:"
    echo "  --pr-only     Create a PR for the release without pushing tags"
    echo "  --help        Show this help message"
    echo ""
    echo "The version tag must follow the format 'vX.Y.Z' where X, Y, Z are numbers."
    echo "For beta releases, use the format 'vX.Y.Z-beta' - these will be marked as pre-releases."
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
        if [[ "$IS_BETA" == "true" ]]; then
            info_log "Beta release detected - allowing release from branch: $current_branch"
        else
            error_log "You are not on the main branch!"
            echo "Current branch: $current_branch"
            echo "Please switch to the main branch before creating a release."
            echo "Or use a beta version (e.g., v1.4.0-beta1) to release from this branch."
            exit 1
        fi
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

# Check if manifest.json exists and is valid
function check_manifest {
    if [[ ! -f "$MANIFEST_PATH" ]]; then
        error_log "Manifest file not found at: $MANIFEST_PATH"
        echo "Please make sure you're running this script from the project root."
        exit 1
    fi
    
    # Check if manifest.json is valid JSON
    if ! cat "$MANIFEST_PATH" | jq . &>/dev/null; then
        error_log "Manifest file is not valid JSON: $MANIFEST_PATH"
        exit 1
    fi
    
    debug_log "Manifest file found and valid: $MANIFEST_PATH"
    return 0
}

# Update version in manifest.json
function update_manifest {
    local version_tag="$1"
    
    # First, check if manifest exists
    check_manifest
    
    # Check if version is already updated
    local current_version=$(grep -o '"version": *"[^"]*"' "$MANIFEST_PATH" | cut -d'"' -f4)
    if [[ "$current_version" == "$version_tag" ]]; then
        info_log "Version is already set to ${version_tag} in manifest.json"
        return 0
    fi

    debug_log "Updating version in: $MANIFEST_PATH"
    
    # Use different sed syntax for macOS vs Linux
    if [[ "$(uname)" == "Darwin" ]]; then
        sed -i '' "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$MANIFEST_PATH"
    else
        sed -i "s|\"version\":.*|\"version\": \"${version_tag}\"|g" "$MANIFEST_PATH"
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
function generate_release_notes {
    local version_tag="$1"
    local release_notes_file=$(mktemp)
    
    info_log "Generating release notes for $version_tag..."
    
    # Add pre-release note for beta versions
    if [[ "$IS_BETA" == true ]]; then
        echo "🔬 **This is a beta release and may contain bugs or incomplete features**" > "$release_notes_file"
        echo "" >> "$release_notes_file"
    fi
    
    # Get the previous tag - ONLY the immediate previous tag
    local prev_tag=$(git describe --abbrev=0 --tags HEAD^ 2>/dev/null || echo "")
    
    # Add header to release notes
    if [[ "$IS_BETA" != true ]]; then
        echo "# ${MAIN_NAME} ${version_tag}" > "$release_notes_file"
    else
        echo "# ${MAIN_NAME} ${version_tag}" >> "$release_notes_file"
    fi
    echo "" >> "$release_notes_file"
    echo "Released on $(date +'%Y-%m-%d')" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Check if there are actual changes
    local change_count=0
    if [[ -n "$prev_tag" ]]; then
        change_count=$(git rev-list --count "$prev_tag..HEAD")
    else
        change_count=$(git rev-list --count HEAD)
    fi
    
    debug_log "Found $change_count changes since previous tag ($prev_tag)"
    
    # If there are no changes, create minimal release notes
    if [[ "$change_count" -eq 0 || "$change_count" -eq 1 ]]; then
        # Only one commit (likely just the version bump)
        echo "## Changes" >> "$release_notes_file"
        echo "" >> "$release_notes_file"
        echo "* Version bump to $version_tag" >> "$release_notes_file"
        echo "" >> "$release_notes_file"
        
        # Add minimal changelog
        if [[ -n "$prev_tag" ]]; then
            echo "## Full Changelog" >> "$release_notes_file"
            echo "[$prev_tag...${version_tag}](https://github.com/enoch85/${REPO_NAME}/compare/${prev_tag}...${version_tag})" >> "$release_notes_file"
        fi
        
        debug_log "Generated minimal release notes (no significant changes)"
        echo "$release_notes_file"
        return
    fi
    
    # There are actual changes, generate meaningful release notes
    echo "## Changes" >> "$release_notes_file"
    echo "" >> "$release_notes_file"
    
    # Try to get meaningful changes using different methods
    local have_changes=false
    
    # 1. Try GitHub PR data if available
    if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
        debug_log "Attempting to get merged PRs using GitHub CLI"
        
        if [[ -n "$prev_tag" ]]; then
            # Get previous tag commit date
            local prev_date=$(git log -1 --format=%aI "$prev_tag")
            debug_log "Previous tag ($prev_tag) date: $prev_date"
            
            # Get and process PRs merged since previous tag
            if prs=$(gh pr list --state merged --base main --json number,title,mergedAt --limit 15 2>/dev/null); then
                debug_log "Successfully retrieved PRs from GitHub"
                
                # Filter to PRs merged after previous tag
                if [[ "$(command -v jq)" && -n "$prs" && "$prs" != "[]" ]]; then
                    # Use jq if available
                    local filtered_prs=$(echo "$prs" | jq -r --arg date "$prev_date" '.[] | select(.mergedAt > $date) | "* " + .title + " (#" + (.number|tostring) + ")"')
                    
                    if [[ -n "$filtered_prs" ]]; then
                        echo "$filtered_prs" >> "$release_notes_file"
                        have_changes=true
                        debug_log "Added PR information to release notes"
                    fi
                fi
            else
                debug_log "Could not retrieve PRs from GitHub"
            fi
        fi
    else
        debug_log "GitHub CLI not available or not authenticated"
    fi
    
    # 2. If we don't have changes yet, use git log to find meaningful commits
    if [[ "$have_changes" != "true" ]]; then
        debug_log "Using git log to find meaningful commits"
        
        # Get non-merge commits since previous tag (or all if no previous tag)
        local commits
        if [[ -n "$prev_tag" ]]; then
            commits=$(git log --no-merges --pretty=format:"* %s (%h)" "$prev_tag..HEAD")
        else
            commits=$(git log --no-merges --pretty=format:"* %s (%h)" -n 10)
        fi
        
        # Filter out automated version bump commits
        local meaningful_commits=$(echo "$commits" | grep -v "Release.*of.*${MAIN_NAME}" | grep -v "Bump version" | head -n 10)
        
        if [[ -n "$meaningful_commits" ]]; then
            echo "$meaningful_commits" >> "$release_notes_file"
            have_changes=true
            debug_log "Added commits to release notes"
        fi
    fi
    
    # 3. If still no changes found, add a fallback message
    if [[ "$have_changes" != "true" ]]; then
        echo "* Minor updates and improvements" >> "$release_notes_file"
        debug_log "No specific changes found, using generic message"
    fi
    
    # Add changelog section
    echo "" >> "$release_notes_file"
    echo "## Full Changelog" >> "$release_notes_file"
    
    if [[ -n "$prev_tag" ]]; then
        echo "[$prev_tag...${version_tag}](https://github.com/enoch85/${REPO_NAME}/compare/${prev_tag}...${version_tag})" >> "$release_notes_file"
    else
        echo "[$version_tag](https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag})" >> "$release_notes_file"
    fi
    
    debug_log "Release notes generated successfully"
    echo "$release_notes_file"
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
    if pr_url=$(gh pr create --base main --head "$branch_name" --title "Release ${version_tag}" --body-file "$release_notes_file"); then
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
    
    if [[ "$IS_BETA" == true ]]; then
        echo -e "${YELLOW}This release will be marked as a pre-release (beta)${NC}"
    fi
    
    success_log "GitHub release will be created automatically by GitHub Actions when tag is pushed"
    echo -e "${BLUE}If you want to review the release after it's created, visit:${NC}"
    echo "https://github.com/enoch85/${REPO_NAME}/releases/tag/${version_tag}"
}

# Creates and pushes a tag
function create_and_push_tag {
    local version_tag="$1"
    local tag_message="Release ${version_tag}"
    
    # For beta versions, add a note in the tag message
    if [[ "$IS_BETA" == true ]]; then
        tag_message="${tag_message} (Beta)"
    fi
    
    info_log "Creating and pushing tag ${version_tag}..."
    if ! git tag -a "${version_tag}" -m "${tag_message}"; then
        error_log "Failed to create tag ${version_tag}"
        return 1
    fi
    
    if ! git push origin "${version_tag}"; then
        error_log "Failed to push tag ${version_tag}"
        return 1
    fi
    
    if [[ "$IS_BETA" == true ]]; then
        success_log "Beta tag ${version_tag} created and pushed (will be marked as pre-release)"
    else
        success_log "Tag ${version_tag} created and pushed"
    fi
    return 0
}

# Check project structure
function check_project_structure {
    # Check if essential directories and files exist
    if [[ ! -d "$INTEGRATION_PATH" ]]; then
        error_log "Integration directory not found: $INTEGRATION_PATH"
        echo "Please make sure you're running this script from the project root."
        exit 1
    fi
    
    if [[ ! -f "$MANIFEST_PATH" ]]; then
        error_log "Manifest file not found: $MANIFEST_PATH"
        echo "Please make sure you're running this script from the project root."
        exit 1
    fi
    
    # Check for README.md and LICENSE - these are included in releases
    if [[ ! -f "README.md" ]]; then
        error_log "README.md not found in project root"
        echo "This file is required for the release package."
        exit 1
    fi
    
    if [[ ! -f "LICENSE" ]]; then
        error_log "LICENSE file not found in project root"
        echo "This file is required for the release package."
        exit 1
    fi
    
    debug_log "Project structure validated"
    return 0
}

# Pull latest changes from remote
function pull_latest_changes {
    info_log "Pulling latest changes..."
    if ! git pull --rebase; then
        error_log "Failed to pull latest changes."
        echo "Please fix the error, then try again."
        exit 1
    fi
    success_log "Latest changes pulled"
    return 0
}

# Main execution function
function run_release_process {
    local version_tag="$1"
    local pr_only="$2"
    
    # Check if this is a beta release first (before any other checks)
    if [[ "${version_tag}" =~ -beta ]]; then
        IS_BETA=true
        info_log "Beta version detected: ${version_tag} - Will be marked as a pre-release"
    fi
    
    # Initial validation checks
    validate_version_tag "$version_tag"
    check_branch
    check_uncommitted_changes
    check_tag_exists "$version_tag"
    check_project_structure
    
    info_log "Starting release process for ${MAIN_NAME} ${version_tag}..."
    
    # Pull latest changes
    pull_latest_changes
    
    # Update manifest.json - returns 0 if already updated, 1 if changes were made
    update_manifest "$version_tag"
    changes_made=$?
    debug_log "Manifest update result: $changes_made (1=changes made, 0=no changes)"
    
    # Generate release notes
    debug_log "Generating release notes..."
    RELEASE_NOTES_FILE=$(generate_release_notes "$version_tag")
    debug_log "Release notes generated at $RELEASE_NOTES_FILE"
    
    # Create either a PR or a full release
    if [[ "$pr_only" == true ]]; then
        info_log "Creating PR only (no tag push)..."
        
        if ! create_release_pr "$version_tag" "$RELEASE_NOTES_FILE"; then
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
            if ! git commit -m "Release ${version_tag} of ${MAIN_NAME}"; then
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
            if ! create_and_push_tag "$version_tag"; then
                error_log "Failed to create and push tag"
                exit 1
            fi
        else
            info_log "No changes to commit. Manifest.json already has version ${version_tag}."
            
            # Display release notes
            info_log "Release Notes:"
            cat "$RELEASE_NOTES_FILE"
            echo
            
            # Confirm tag creation
            read -p "Do you want to create and push the tag ${version_tag}? (y/n): " -n 1 -r
            echo
            if [[ ! $REPLY =~ ^[Yy]$ ]]; then
                echo "Aborting release process."
                exit 1
            fi
            
            # Create and push tag
            if ! create_and_push_tag "$version_tag"; then
                error_log "Failed to create and push tag"
                exit 1
            fi
        fi
    
        # Create GitHub release (now just displays a notice)
        create_github_release "$version_tag" "$RELEASE_NOTES_FILE"
    
        if [[ "$IS_BETA" == true ]]; then
            success_log "${MAIN_NAME} ${version_tag} (BETA) successfully prepared!"
            echo -e "${BLUE}The GitHub Actions workflow will now create the pre-release.${NC}"
        else
            success_log "${MAIN_NAME} ${version_tag} successfully prepared!"
            echo -e "${BLUE}The GitHub Actions workflow will now create the actual release.${NC}"
        fi
        echo -e "${BLUE}You can monitor the process at:${NC} https://github.com/enoch85/${REPO_NAME}/actions"
    fi
    
    # Clean up temporary file
    if [[ -f "$RELEASE_NOTES_FILE" ]]; then
        debug_log "Cleaning up temporary release notes file"
        rm "$RELEASE_NOTES_FILE"
    fi
    
    success_log "Release script completed successfully."
    return 0
}

# Main execution starts here

# Check for required tools
check_github_cli
check_jq

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

# Start the release process
run_release_process "$VERSION_TAG" "$PR_ONLY"
