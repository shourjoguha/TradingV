# Recipes (cookbook)

How to do common things, with the existing pattern to mirror. Each recipe assumes you've read [principles.md](principles.md) and [architecture.md](architecture.md). Each is < 10 lines because every recipe links to a working example in the codebase.

---

## Add a new endpoint

1. Pick a module (`app/<feature>/`). If new feature → create the package.
2. `routes.py` — add the route handler. Always add `_api_key: str = Depends(verify_api_key)`.
3. `service.py` — pure async functions returning dicts/models. No FastAPI imports.
4. Register the router in `app/api/router.py` (under `v1_router`).
5. Tests in `tests/test_<module>.py`. Use the `client` fixture from `conftest.py`.

**Mirror**: [`app/accuracy/routes.py`](../app/accuracy/routes.py) is a clean example.

## Add a new lifespan background task

1. Implement the loop in your module: `async def my_loop(*, stop_event: asyncio.Event = None)`. Always cancellation-safe.
2. In `app/main.py` lifespan, after the existing tasks: `stop_event = asyncio.Event(); task = asyncio.create_task(my_loop(stop_event=stop_event), name="my-loop")`.
3. Clean shutdown: `stop_event.set(); task.cancel()` in the lifespan teardown.
4. Tolerant of missing config — no-op rather than crash. Pattern: `if not configured(): return`.

**Mirror**: [`app/accuracy/service.py::evaluator_loop`](../app/accuracy/service.py).

## Add a new migration

1. Increment version: next file is `migrations/versions/<NNNN>_<description>.py`.
2. Set `down_revision` to the prior version. Hand-edit; autogenerate isn't wired.
3. `def upgrade()` and `def downgrade()` both required.
4. Postgres-only DDL? Branch on `bind.dialect.name` — see [`migrations/versions/0006_replication_extensions.py`](../migrations/versions/0006_replication_extensions.py).
5. Run `alembic upgrade head` locally. Add the model class to `app/<module>/models.py` + import in `app/main.py` + `tests/conftest.py`.
6. Document in [migrations.md](migrations.md).

**Mirror**: [`migrations/versions/0017_submit_queue.py`](../migrations/versions/0017_submit_queue.py).

## Add a new frontend page

1. `frontend/src/pages/<Name>.tsx` — function component. Use existing hooks from `hooks/use-api.ts`.
2. Add the route in `frontend/src/App.tsx`.
3. Add nav entry in `frontend/src/components/Layout.tsx` `NAV` array (path, label, lucide icon).
4. Follow the neumorphic patterns: `rounded-2xl`/`rounded-3xl`, `shadow-extruded`/`shadow-inset`, no `border` utilities — see [frontend/ui-components.md](frontend/ui-components.md).
5. Empty state: dashed-border replaced by `shadow-inset-sm` cards.

**Mirror**: [`frontend/src/pages/Accuracy.tsx`](../frontend/src/pages/Accuracy.tsx).

## Add a new ui/ primitive

1. `frontend/src/components/ui/<name>.tsx` — wrap a Radix primitive with `cva` variants + `cn()`.
2. Apply neumorphic shadows: `shadow-extruded-sm` at rest, `shadow-extruded` on hover, `shadow-inset-sm` on press/active.
3. `rounded-2xl` minimum (12px); `rounded-3xl` for cards.
4. Focus state: `focus-visible:ring-2 focus-visible:ring-violet focus-visible:ring-offset-2`.
5. NO `bg-white`, NO bare `border` utilities.

**Mirror**: [`frontend/src/components/ui/button.tsx`](../frontend/src/components/ui/button.tsx).

## Add a new background-job source (queue enqueue)

1. From your code: `from app.queue import service as queue_svc; await queue_svc.enqueue(inputs={...}, source="<your_source>")`.
2. Allowed sources are an enum: `manual` | `schedule` | `fallback`. Add a new variant in [`app/queue/service.py`](../app/queue/service.py) if needed.
3. The worker auto-drains FIFO — no extra wiring.

**Mirror**: [`app/schedule/runner.py::_tick`](../app/schedule/runner.py).

## Add a new TanStack Query hook

1. Add the type to `frontend/src/lib/types.ts`.
2. In `frontend/src/hooks/use-api.ts`, write `useFoo()` that calls `apiFetch<FooResponse>(...)`. Always key the queryKey by `backendId` from `useBackend()`.
3. Mutations: `onSuccess` invalidates the list query; `toast.success(...)`. `onError`: `toast.error(...)`.
4. Polling? `refetchInterval: 5000` (queue widget) or `60000` (most lists). Stop polling on terminal states by returning `false` from the function form.

**Mirror**: [`useQueueItem` in `hooks/use-api.ts`](../frontend/src/hooks/use-api.ts) (auto-stops polling).

## Wire a new Telegram alert

1. In your module: `from app.notifications import telegram; await telegram.send_message("Markdown text")`.
2. No-op when unconfigured (TELEGRAM_BOT_TOKEN/CHAT_ID empty). Don't add your own configured-check; the notifier handles it.
3. Returns `bool`; never raises.

**Mirror**: [`app/accuracy/drift.py::_notify_drifts`](../app/accuracy/drift.py).

## Add a new metric to the accuracy/opportunities/trades flow

1. Pure-math first: write the formula in a unit-testable helper. See `_compute_metrics` in [`app/accuracy/service.py`](../app/accuracy/service.py).
2. Aggregate at query time (not at write time) — see `accuracy_grid()`.
3. Add a column on `prediction_accuracy` only if the per-row math can't be re-derived.
4. UI: extend the existing hook; add the field to the heatmap drilldown.

**Mirror**: how `direction_correct` was added: column → math helper → aggregate in `accuracy_grid` → drilldown table renders it.

## Add a new ADR

1. `.claude/decisions/<NNN>-<short-slug>.md`. NNN = next sequential.
2. Use the template at the top of [decisions/000-template.md](decisions/000-template.md).
3. Required fields: date, context, options considered, choice, trigger to revisit, files affected.
4. Cross-link from any module doc + backlog/tech_debt entry that references the decision.

**Mirror**: [decisions/001-cf-pages-over-lovable.md](decisions/001-cf-pages-over-lovable.md).
