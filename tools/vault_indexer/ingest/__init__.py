"""Ingestion workers — produce markdown into the vault.

Each script takes operator input (a path / URL / hint) and writes one or
more markdown files into the vault under the appropriate folder. The
indexer's watch loop picks them up; a manual `POST /reload` is also valid.
"""
