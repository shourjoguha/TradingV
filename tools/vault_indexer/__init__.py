"""vault-indexer — local FastAPI sidecar over an Obsidian vault.

Phase 2 of the macro-workbench → decision-tool roadmap. Watches the
operator's vault at $VAULT_PATH for changes, embeds notes via
sentence-transformers, exposes search/traverse/node endpoints, and
manages the operator-in-the-loop review queue + tag taxonomy.

Run as a separate process on port 8001:

    uvicorn tools.vault_indexer.app:app --port 8001 --reload

Reads $VAULT_PATH, $INDEXER_DB_PATH, $ANTHROPIC_API_KEY, $EMBEDDING_MODEL.
"""
