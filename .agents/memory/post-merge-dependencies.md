---
name: Post-merge dependencies
description: Nix-safe Python dependency installation and package-firewall handling for this workspace's post-merge hook.
---

Post-merge Python installs must target the project-local `.pythonlibs/lib/pythonX.Y/site-packages`; bare system `pip install` is blocked because the Nix store is immutable. Do not bypass this with `--break-system-packages`.

When Replit's npm firewall blocks a locked transitive package version, identify its parent, check the package maintainer's security guidance, and update to a compatible fixed version. Keep `package-lock.json` tarball URLs on the public npm registry for deployment portability.

**Why:** The first hook run hit PEP 668 on system Python, and the next exposed a firewall block on a vulnerable transitive npm release.

**How to apply:** Use the project-local Python target in `scripts/post-merge.sh`; configure the hook with `setPostMergeConfig`, then verify both setup and workflow reconciliation with `runPostMergeSetup`.
