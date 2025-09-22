# FusionX Backend Roadmap

_Last updated: 2024-02-16_

## Legend
- [x] Completed
- [ ] Planned / Not started
- [ ] (In progress) – annotate with text

## Phase 0 – Baseline Platform (Complete)
- [x] FastAPI application skeleton with SQLModel persistence layer
- [x] Token-based staff authentication with password hashing
- [x] Device registration for TruckKDS clients
- [x] Truck shift lifecycle (check-in, checkout, pause, resume)
- [x] Menu retrieval and inventory adjustments per shift
- [x] KDS ticket feed with guarded order state transitions
- [x] WebSocket hub for real-time shift events
- [x] Developer seed script and simulated order generator

## Phase 1 – Operational MVP (In progress)
- [x] Provide mobile endpoint to list active trucks a staff member can act on (Iteration 1)
- [x] Provide mobile endpoint to list active service locations for shift check-in (Iteration 1)
- [ ] Add per-shift summary endpoint (order counts, revenue, average prep time)
- [ ] Expose staff-accessible configuration for throttle and slot capacity adjustments
- [ ] Deliver heartbeat endpoint so devices can report liveness / capture last_seen timestamps

## Phase 2 – Menu & Inventory Management
- [ ] CRUD endpoints for menu items (name, description, base price)
- [ ] Support menu categories and ordering for TruckKDS display
- [ ] Allow per-shift specials (temporary items) and schedule-based availability windows
- [ ] Atomic stock decrements tied to payment notifications from customer ordering flow

## Phase 3 – Order Lifecycle Enhancements
- [ ] Dedicated order detail endpoint with customer contact information and item modifiers
- [ ] Ability to place tickets on hold / resume for timed prep coordination
- [ ] Cancellation & refund reasons with audit trail and metrics
- [ ] Bulk advance endpoint for clearing multiple READY tickets at closeout

## Phase 4 – Notifications & Staff Experience
- [ ] APNs push notification service for new orders and low stock alerts
- [ ] Device management console (list / revoke tokens, capture app version & OS)
- [ ] Optional SMS fallback alerts for low connectivity trucks
- [ ] Staff profile endpoint for updating password, preferred notification channels

## Phase 5 – Administration & Access Control
- [ ] Admin API for managing trucks, locations, staff assignments, and operating hours
- [ ] Role-based access control enforcement (per-route permissions)
- [ ] Audit logging for privileged operations (menu edits, refunds, shift overrides)

## Phase 6 – Reporting & Analytics
- [ ] Shift history export (CSV/JSON) with order, labor, and inventory deltas
- [ ] Real-time dashboard endpoints (current order throughput, wait times)
- [ ] Weekly automated summary email (orders, revenue, stock-outs)

## Phase 7 – Reliability, Observability & Deployment
- [ ] Structured logging with correlation IDs for each request / websocket session
- [ ] Metrics instrumentation (Prometheus) for API latency, DB usage, and queue depth
- [ ] Healthcheck & readiness endpoints for container orchestration
- [ ] Harden configuration management (12-factor env vars, secrets, migrations)
- [ ] CI pipeline (lint, tests, image build, deployment manifest)

## Phase 8 – Quality Assurance & Developer Experience
- [ ] Unit test coverage for auth, shift, menu, and order flows
- [ ] Contract tests for mobile API schema stability
- [ ] Load testing scenarios to validate throughput at peak events
- [ ] API documentation (OpenAPI polish, endpoint usage guides)
- [ ] Local development scripts (make targets, sample data refresh, watch mode)

## Phase 9 – Customer Ordering Integration (Stretch)
- [ ] Customer-facing ordering API (menu browsing, cart, checkout)
- [ ] Payment gateway webhook integration for order confirmation
- [ ] Auto-reconciliation of customer orders with KDS queue
- [ ] Loyalty / rewards tracking hooks for repeat guests

---

### Iteration History
- **Iteration 1 (2024-02-16):** Bootstrapped roadmap, added truck & location discovery endpoints for the mobile client, refreshed README to describe available capabilities.
