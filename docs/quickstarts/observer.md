# Quickstart: observer profile

Watch only. Orbit desktop with boards, agent sessions and the activity view — no execution system
attached. Manifest: [../../profiles/observer.json](../../profiles/observer.json).

## Honest status first

The runnable-by-anyone first run for Orbit is **not landed**. `main` was reconciled with the live tree
on November 12 (orbitdesktop PR 24), and the onboarding-wizard work is in progress (chapter 15 and
chapter 17 of the docs). There is no verified one-command install in this umbrella yet, so this
quickstart stops at what is verifiable from here and hands you to the checkout's own docs.

## 1. Clone and confirm what you have

```bash
git clone https://github.com/mojomast/orbitdesktop
cd orbitdesktop
git log --oneline -1
```

If the head includes the November 12 reconcile, you are on the tree that actually ran, not the stale
October `main`.

## 2. Start the app from its own documentation

The orbitdesktop checkout carries the authoritative run and configuration docs — its QUICKSTART and
CONFIG documents under its docs folder. Follow those; this umbrella does not quote commands it cannot
verify from here. The dispatch manifest recorded in this repo
(`contrib/bee-ci/jobs/orbitdesktop.yaml`) declares the CI legs — unit, browser-e2e and python-launcher,
Python 3.12 and Node 22, chromium for the browser-e2e leg — but declares eligibility only, not commands.

## 3. What an observer install looks like

With no execution system attached you can still:

- read and organize collaboration boards;
- hold agent sessions (Grok Bots, Hermes, Pi and other adapters);
- watch the activity view.

## What this profile cannot do

- Cannot create, dispatch or verify attempts — that is the orchestrator profile.
- Cannot prove any work happened: a board status is never evidence that work completed.
- Cannot run a first-run wizard: that work is in progress, not merged.
- The browser-e2e suite needs a chromium-capable environment; nothing here installs a browser for you.
