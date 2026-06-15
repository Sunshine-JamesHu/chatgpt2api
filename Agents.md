# Agent Notes

## Release Packaging

- Before creating a release package, fetch the cloud `main` branch, update local `main`, merge `main` into `develop`, and package from the merged `develop` branch.
- Use the upstream `VERSION` value plus the local package suffix for artifacts, for example `1.5.0-c1`.
