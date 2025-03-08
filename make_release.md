# How to Create a New Release

After applying the fixes, here's the recommended release process:

## Option 1: Using the Release Script (Recommended)

### A. Create and Review the PR First
1. Run the script with `--pr-only` flag:
   ```bash
   bash release.sh v0.3.11 --pr-only
   ```
2. This will:
   - Update the version in manifest.json
   - Create a release branch
   - Push the branch to GitHub
   - Create a PR for the release

3. Review the PR on GitHub
4. Merge the PR into main

### B. Create the Release Tag
1. Pull the latest changes to your local main branch:
   ```bash
   git checkout main
   git pull origin main
   ```

2. Run the script without flags to create the tag:
   ```bash
   bash release.sh v0.3.11
   ```
3. The script will:
   - Recognize the version is already updated
   - Ask you to confirm tag creation
   - Create and push the tag
   - The GitHub Actions workflow will create the actual release

## Option 2: Manual Approach (If Script Has Issues)

1. Update the version in manifest.json:
   ```bash
   # Edit the file and change the version
   git add custom_components/ovms/manifest.json
   git commit -m "Bump version to v0.3.11"
   git push origin main
   ```

2. Create and push a tag:
   ```bash
   git tag v0.3.11
   git push origin v0.3.11
   ```

3. The GitHub Actions workflow will automatically create the release when it detects the new tag.

## Verifying Your Release

After pushing the tag:
1. Go to the GitHub repository
2. Navigate to "Actions" tab to monitor the workflow
3. Once completed, check the "Releases" section to verify your new release was created

