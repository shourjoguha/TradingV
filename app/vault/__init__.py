"""Read-only proxy to the vault-indexer sidecar (port 8001).

Keeps the indexer port out of the frontend bundle and provides one
authenticated surface (``/v1/vault/*``) for every consumer that wants
semantic search, folder-context vignettes, or single-node markdown bodies.
"""
