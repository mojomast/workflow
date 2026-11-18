# Reproduce the offline Orbit check

Run `npm run check` against a disposable snapshot of **one** reviewed Orbit working tree. Use a trusted Linux/amd64 Debian 13 runner with Bash, Python 3.11+, Git, Docker, dpkg-deb and several GiB of scratch space. The checkout must have the Git fixture objects named in `snapshot.py` (a shallow clone may not). The script never pulls an image or downloads a package.

### Provision local inputs

- Preload the `linux/amd64` `python:3.12-slim` image from `python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`. The scripts check its immutable local image ID.
- Provide stock Debian Git (tested with 2.47.3), OpenSSH client/server (10.0p2), Git templates and system tools listed in `prepare.sh`. Use a clean package installation, not a personal tools directory. Set `ORBIT_TMUX_DEB` to the local Debian `tmux_3.5a-3_amd64.deb`. Setup verifies the package digest.
- Put the pinned Node 22.23.5 binary and npm 10.8.2 on `PATH`, or set `ORBIT_NODE_BINARY` and `ORBIT_NPM_DIR` (the npm package directory containing `bin/npm-cli.js`). The script verifies the Node binary digest and npm version. Use an unmodified npm distribution without user configuration.
- Pre-provision Orbit's lock-matched `node_modules`, including the two pinned Linux native addons (`better-sqlite3` and `node-pty`), and the corresponding public package tarballs in the npm cache. If using a nondefault cache, set `ORBIT_NPM_CACACHE` to its `_cacache` directory. Only SHA-512-verified, lock-selected tarballs and the two SHA-256-verified addons go into the kit. A missing required package or digest mismatch stops setup. Optional packages not installed for this platform can remain absent. Rebuild the kit after a lockfile change; review pins on a deliberate dependency/ABI change.

### Prepare and run

From the **parent** of the four checkouts, with inputs available on the local Docker host:

```bash
runner=workflow/contrib/core-review/orbit-check
: "${ORBIT_TMUX_DEB:?set to the local pinned tmux deb}"
export ORBIT_TMUX_DEB
kit=$(bash "$runner/prepare.sh" orbitdesktop) || exit 1
bash "$runner/run.sh" preflight "$kit" orbitdesktop "$runner/buildout.paths" &&
  bash "$runner/run.sh" check "$kit" orbitdesktop "$runner/buildout.paths"
```

`preflight` checks the archived Git fixtures, offline npm install, native modules, contract generation, tmux, sshd, schema migration/restore, and IRC. `check` runs the ordinary package command. Both propagate failure. `TMPDIR` selects the local scratch parent (default `/var/tmp`). The runner prints a new private evidence directory containing `snapshot.json` (base, per-file hashes and deletions) and a command log. Keep logs, snapshots, and the reusable kit out of Git. The container and exported source are removed on normal exit. Delete the evidence and kit when no longer needed.

### Review what runs

Use a quiescent Orbit checkout. Inspect `git -C orbitdesktop ls-files --others --exclude-standard` and the **contents** of any proposed additions before editing `buildout.paths`. Entries are individual repo-relative files; tracked entries are also accepted. No directories, globs, symlinks or ignored files. An unlisted supported source file, missing manifest entry or restricted source path stops the snapshot. Do not generate the manifest from the entire untracked list. For an intentional new file type, review `extra()` in `snapshot.py`.

The private snapshot includes checked-out tracked bytes (including Orbit's tracked archive), deletions, reviewed additions, and Git objects for HEAD/index and named test fixtures. It does not use host Git config or remotes. Source, kit and `inside.sh` are mounted read-only; the container copies them into its own writable filesystem. Docker runs with `--network=none --pull=never --init --pids-limit=640 --memory=6g --cpus=3 --security-opt=no-new-privileges`. No host home, agent, service socket or live workspace is mounted. See the [overview](../README.md) for measured results and open gates.
