"""Miniature, offline reference workflow.

This package is a runnable sketch of the protocol in the parent docs:
contracts and leases first, isolated workers, independent verification,
integration on the combined result, and a metrics log.

It does not implement production bundlebees or Orbit, talk to a network,
or load a model. Workers are scripted patch generators.

Teaching only: lease fingerprints are unkeyed SHA-256 hashes that anyone who
can edit the store can recompute. Use bundlebees' HMAC-signed leases for real
enforcement.
"""

__all__ = ["orchestrator"]
