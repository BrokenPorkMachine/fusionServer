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
- `GET /api/mobile/shift/{id}/menu` — fetch base menu items with per-shift overrides
- `PATCH /api/mobile/shift/{id}/inventory` — bulk update stock counts and sold-out flags

### Kitchen Display & Orders
- `GET /api/mobile/shift/{id}/kds` — aggregated ticket queue ordered by creation time
- `POST /api/mobile/order/{order_id}/advance` — guarded order state transitions

### Real-time Events
- `WS /api/mobile/ws/shift/{id}` — low stock, pause/resume, and new order notifications for TruckKDS

### Developer & Testing Utilities
- `POST /dev/seed` — seed baseline trucks, staff, locations, and menu items
- `POST /dev/sim-order/{shift_id}` — create a simulated paid order and push a KDS notification

## Getting Started
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # adjust environment variables as needed
make run
```
Open http://127.0.0.1:8000 for automatic FastAPI docs.

### Seed the database
```bash
make seed
# username: chef   password: password
```

## Development Notes
- The project uses [FastAPI](https://fastapi.tiangolo.com/) with [SQLModel](https://sqlmodel.tiangolo.com/) for persistence.
- Run `make fmt` to apply basic formatting (Black) to the `app/` package.
- Configure environment variables via `.env`; see `app/config.py` for supported keys.

## Roadmap
The long-term roadmap lives in [`ROADMAP.md`](ROADMAP.md). Each iteration updates the roadmap and this README as new features
ship.

## Production Considerations
- Replace the ad-hoc token system with JWT/OIDC and revoke-on-demand.
- Migrate from SQLite to Postgres with migrations.
- Add APNs push delivery, API rate limiting, and per-route authorization controls.
- Enforce atomic inventory adjustments once customer ordering is wired in.
