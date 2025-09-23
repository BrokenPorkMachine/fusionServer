# FusionX — FastAPI server for roaming food truck ordering

FusionX powers the TruckKDS mobile experience for roaming food truck crews. The service focuses on staff
operations (authentication, shift management, menu + inventory, kitchen display, and real-time updates) so
teams can keep up with high-volume events.

## Currently Available

### Authentication & Devices
- `POST /api/mobile/login` — username/password login that returns a bearer token and staff profile
- `POST /api/mobile/devices/register` — register APNs tokens for the signed-in staff member
- `POST /api/mobile/devices/heartbeat` — capture liveness pings to record `last_seen` timestamps for devices

### Shift Operations
- `GET /api/mobile/trucks` — list active trucks the staff member can operate
- `GET /api/mobile/locations` — list service locations for shift check-in
- `GET /api/mobile/shift/active` — fetch the most recent shift for the staff member's truck
- `POST /api/mobile/shift/checkin` — begin a shift at a location
- `POST /api/mobile/shift/{id}/checkout` — close out a shift and notify connected devices
- `POST /api/mobile/shift/{id}/pause` / `POST /api/mobile/shift/{id}/resume` — manage temporary pauses
- `GET /api/mobile/shift/{id}/config` — view throttle and slot capacity configuration for the shift
- `PATCH /api/mobile/shift/{id}/config` — adjust throttle/slot capacity values in real time
- `GET /api/mobile/shift/{id}/summary` — aggregate order counts, revenue, and average prep time metrics

### Menu & Inventory
- `GET /api/mobile/shift/{id}/menu` — fetch base menu items with per-shift overrides and specials
- `PATCH /api/mobile/shift/{id}/inventory` — bulk update stock counts and sold-out flags (records inventory adjustments)
- `POST /api/menu/items` / `PATCH /api/menu/items/{id}` / `DELETE /api/menu/items/{id}` — manage core menu catalog
- `POST /api/menu/categories` — maintain menu categories and ordering for the KDS
- `POST /api/menu/shift/{id}/specials` — create per-shift specials with availability windows

### Kitchen Display & Orders
- `GET /api/mobile/shift/{id}/kds` — aggregated ticket queue ordered by creation time
- `POST /api/mobile/order/{order_id}/advance` — guarded order state transitions
- `GET /api/mobile/order/{order_id}` — enriched order detail for TruckKDS actions
- `POST /api/mobile/order/{order_id}/hold` / `POST /api/mobile/order/{order_id}/resume` — pause/resume timed prep
- `POST /api/mobile/order/{order_id}/cancel` — capture cancellation or refund reasons
- `POST /api/mobile/shift/{id}/advance-ready` — bulk close out READY tickets at shift end

### Real-time Events
- `WS /api/mobile/ws/shift/{id}` — low stock, pause/resume, and new order notifications for TruckKDS

### Devices & Staff
- `GET /api/mobile/devices` / `DELETE /api/mobile/devices/{id}` — manage device tokens per staff member
- `PATCH /api/mobile/staff/profile` — update phone, notification channel, and password preferences

### Developer & Testing Utilities
- `POST /dev/seed` — seed baseline trucks, staff, locations, and menu items
- `POST /dev/sim-order/{shift_id}` — create a simulated paid order and push a KDS notification

### Admin & Analytics
- `GET /api/admin/trucks` / `POST /api/admin/trucks` — manage fleet metadata
- `PUT /api/admin/trucks/{id}/hours` — capture weekly operating hours per truck
- `GET /api/admin/audit-logs` — review privileged activity
- `GET /api/analytics/shift/{id}/dashboard` — real-time throughput and low stock metrics
- `GET /api/analytics/shift/{id}/export` — export shift history as JSON or CSV
- `POST /api/analytics/weekly-summary` — generate weekly revenue/stock summary payloads

### Customer Ordering
- `GET /api/customer/menu/{shift_id}` — menu view tailored for guests
- `POST /api/customer/order` — accept customer-facing orders and modifiers
- `POST /api/customer/payment/webhook` — atomically confirm payment and decrement stock
- `POST /api/customer/reconcile` — auto-reconcile paid tickets into the production queue
- `GET /api/customer/loyalty/{phone}` — inspect loyalty ledger totals

### Health & Telemetry
- `GET /healthz` / `GET /readyz` — container health + readiness
- `GET /metrics` — Prometheus scrape endpoint with request and websocket metrics

## Getting Started
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adjust environment variables as needed
make run  # or `make check` to run formatting + tests
```
Open http://127.0.0.1:8000 for automatic FastAPI docs.

### Seed the database
```bash
make seed
# username: chef   password: password
```

## Development Notes
- The project uses [FastAPI](https://fastapi.tiangolo.com/) with [SQLModel](https://sqlmodel.tiangolo.com/) for persistence.
- Run `make fmt` to apply basic formatting (Black) to `app/` and `tests/`.
- Run `make test` to execute the pytest suite, or `make check` for formatting + tests.
- Configure environment variables via `.env`; see `app/config.py` for supported keys.
- Structured logging adds a correlation ID to every request and websocket connection, surfaced via the `x-request-id` header and exported metrics.

## Roadmap
The long-term roadmap lives in [`ROADMAP.md`](ROADMAP.md). Each iteration updates the roadmap and this README as new features
ship.

## Production Considerations
- Replace the ad-hoc token system with JWT/OIDC and revoke-on-demand.
- Migrate from SQLite to Postgres with migrations.
- Add APNs push delivery, API rate limiting, and per-route authorization controls.
- Enforce atomic inventory adjustments once customer ordering is wired in.
