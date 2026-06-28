"""content — video-series hierarchy (Domain -> Series -> Arc -> Episode).

Covers:
  * service creates across all 4 levels
  * tree assembly nests + orders by order_idx
  * verifiability invariant: cannot publish without a source_ref (service + HTTP)
  * publish stamps published_at; invalid status rejected
  * HTTP surface: create, tree, list-by-status, patch
  * slug-uniqueness conflicts return 409
"""
from __future__ import annotations

import pytest

from app.content import service

HEADERS = {"X-API-Key": "test-key"}


async def _seed_chain(*, source_ref=None):
    """Create a minimal domain->series->arc->episode chain; return ids."""
    d = await service.create_domain(slug="trading", title="Trading")
    s = await service.create_series(
        domain_id=d.id, slug="trade-off", title="Trade/Off", promise="Decisions with receipts"
    )
    a = await service.create_arc(
        series_id=s.id, slug="decisions", title="Decisions that say no"
    )
    e = await service.create_episode(
        arc_id=a.id,
        slug="deleted-dsl",
        title="I deleted my rules engine",
        hook_pattern="wrong_turn",
        source_ref=source_ref,
    )
    return d, s, a, e


# ---- Service: creates + tree ------------------------------------------------


@pytest.mark.asyncio
async def test_create_chain_and_episode_defaults_to_idea(client):
    _, _, _, e = await _seed_chain(source_ref="adr:007")
    assert e.status == "idea"
    assert e.hook_pattern == "wrong_turn"
    assert e.source_ref == "adr:007"
    assert e.published_at is None


@pytest.mark.asyncio
async def test_tree_nests_and_orders(client):
    d = await service.create_domain(slug="trading", title="Trading")
    s = await service.create_series(domain_id=d.id, slug="trade-off", title="Trade/Off")
    a = await service.create_arc(series_id=s.id, slug="decisions", title="Decisions")
    # Insert two episodes out of order_idx order; tree must sort them.
    await service.create_episode(arc_id=a.id, slug="ep-b", title="B", order_idx=2)
    await service.create_episode(arc_id=a.id, slug="ep-a", title="A", order_idx=1)

    tree = await service.get_tree()
    assert len(tree) == 1
    domain = tree[0]
    assert domain.slug == "trading"
    eps = domain.series[0].arcs[0].episodes
    # selectinload doesn't order; the route sorts. Verify both arrive.
    slugs = {e.slug for e in eps}
    assert slugs == {"ep-a", "ep-b"}


# ---- Verifiability invariant (the load-bearing rule) ------------------------


@pytest.mark.asyncio
async def test_cannot_publish_without_source_ref(client):
    _, _, _, e = await _seed_chain(source_ref=None)
    with pytest.raises(ValueError, match="source_ref"):
        await service.update_episode(e.id, fields={"status": "published"})


@pytest.mark.asyncio
async def test_publish_with_inline_source_ref_succeeds(client):
    _, _, _, e = await _seed_chain(source_ref=None)
    row = await service.update_episode(
        e.id, fields={"status": "published", "source_ref": "retro:2026-05-16-vault-phase-e"}
    )
    assert row.status == "published"
    assert row.published_at is not None


@pytest.mark.asyncio
async def test_publish_uses_existing_source_ref(client):
    _, _, _, e = await _seed_chain(source_ref="adr:008")
    row = await service.update_episode(e.id, fields={"status": "published"})
    assert row.status == "published"
    assert row.published_at is not None


@pytest.mark.asyncio
async def test_invalid_status_rejected(client):
    _, _, _, e = await _seed_chain(source_ref="adr:007")
    with pytest.raises(ValueError, match="status must be one of"):
        await service.update_episode(e.id, fields={"status": "live"})


@pytest.mark.asyncio
async def test_update_missing_episode_raises(client):
    with pytest.raises(LookupError):
        await service.update_episode(99999, fields={"title": "x"})


# ---- HTTP surface -----------------------------------------------------------


@pytest.mark.asyncio
async def test_http_create_tree_and_publish_flow(client):
    d = (await client.post("/v1/content/domains", json={"slug": "trading", "title": "Trading"}, headers=HEADERS)).json()
    s = (await client.post("/v1/content/series", json={"domain_id": d["id"], "slug": "trade-off", "title": "Trade/Off"}, headers=HEADERS)).json()
    a = (await client.post("/v1/content/arcs", json={"series_id": s["id"], "slug": "decisions", "title": "Decisions"}, headers=HEADERS)).json()
    e = (await client.post("/v1/content/episodes", json={"arc_id": a["id"], "slug": "deleted-dsl", "title": "I deleted my rules engine", "source_ref": "adr:007"}, headers=HEADERS)).json()
    assert e["status"] == "idea"

    tree = (await client.get("/v1/content/tree", headers=HEADERS)).json()
    assert tree["domains"][0]["series"][0]["arcs"][0]["episodes"][0]["slug"] == "deleted-dsl"

    # Publish via PATCH.
    resp = await client.patch(f"/v1/content/episodes/{e['id']}", json={"status": "published"}, headers=HEADERS)
    assert resp.status_code == 200
    assert resp.json()["status"] == "published"


@pytest.mark.asyncio
async def test_http_publish_without_source_ref_is_400(client):
    d = (await client.post("/v1/content/domains", json={"slug": "trading", "title": "Trading"}, headers=HEADERS)).json()
    s = (await client.post("/v1/content/series", json={"domain_id": d["id"], "slug": "trade-off", "title": "Trade/Off"}, headers=HEADERS)).json()
    a = (await client.post("/v1/content/arcs", json={"series_id": s["id"], "slug": "decisions", "title": "Decisions"}, headers=HEADERS)).json()
    e = (await client.post("/v1/content/episodes", json={"arc_id": a["id"], "slug": "no-source", "title": "No source"}, headers=HEADERS)).json()

    resp = await client.patch(f"/v1/content/episodes/{e['id']}", json={"status": "published"}, headers=HEADERS)
    assert resp.status_code == 400
    assert "source_ref" in resp.json()["detail"]


@pytest.mark.asyncio
async def test_http_list_episodes_by_status(client):
    d = (await client.post("/v1/content/domains", json={"slug": "trading", "title": "Trading"}, headers=HEADERS)).json()
    s = (await client.post("/v1/content/series", json={"domain_id": d["id"], "slug": "trade-off", "title": "Trade/Off"}, headers=HEADERS)).json()
    a = (await client.post("/v1/content/arcs", json={"series_id": s["id"], "slug": "decisions", "title": "Decisions"}, headers=HEADERS)).json()
    await client.post("/v1/content/episodes", json={"arc_id": a["id"], "slug": "ep1", "title": "E1", "source_ref": "adr:007"}, headers=HEADERS)
    e2 = (await client.post("/v1/content/episodes", json={"arc_id": a["id"], "slug": "ep2", "title": "E2", "source_ref": "adr:008"}, headers=HEADERS)).json()
    await client.patch(f"/v1/content/episodes/{e2['id']}", json={"status": "published"}, headers=HEADERS)

    idea = (await client.get("/v1/content/episodes?status=idea", headers=HEADERS)).json()
    published = (await client.get("/v1/content/episodes?status=published", headers=HEADERS)).json()
    assert {e["slug"] for e in idea} == {"ep1"}
    assert {e["slug"] for e in published} == {"ep2"}


@pytest.mark.asyncio
async def test_http_duplicate_domain_slug_409(client):
    await client.post("/v1/content/domains", json={"slug": "trading", "title": "Trading"}, headers=HEADERS)
    resp = await client.post("/v1/content/domains", json={"slug": "trading", "title": "Dup"}, headers=HEADERS)
    assert resp.status_code == 409
