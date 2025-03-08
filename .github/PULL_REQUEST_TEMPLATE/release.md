---
name: Release
about: Use this template for release PRs
title: 'Release [VERSION]'
labels: release
assignees: ''
---

# Release PR Checklist

## Version Information
- [ ] Version number updated in `manifest.json`
- [ ] Version follows semantic versioning: `vX.Y.Z`
  - Major version (X): Breaking changes
  - Minor version (Y): New features, non-breaking
  - Patch version (Z): Bug fixes and small improvements

## Quality Checks
- [ ] All automated tests pass
- [ ] Manual testing completed with Home Assistant
- [ ] Documentation updated
- [ ] Release notes reviewed and accurate

## Breaking Changes
If this release contains breaking changes, list them here:
- None

## Migration Instructions
If users need to take action when upgrading, describe the steps here:
- No migration needed

## Additional Notes
<!-- Add any additional notes for reviewers or users here -->
