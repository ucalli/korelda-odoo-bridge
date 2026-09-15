# KORELDA Bridge — Alarm to Maintenance

Odoo module that receives **signed webhooks** from a KORELDA
building-management installation and opens a **maintenance request** for each
HVAC alarm.

KORELDA monitors HVAC plant over **Modbus TCP** (air handling units, pool
climate units and similar) and raises alarms from its own rules. This module
is the Odoo-side receiver for those alarms.

## What it does

| | |
|---|---|
| Endpoint | Listens for alarm events over HTTP(S). |
| Authentication | **HMAC-SHA256** signature on the raw request body. |
| Rejects | Unsigned, mis-signed, stale (older than 5 minutes) and replayed deliveries. |
| Creates | A `maintenance.request`, with alarm severity mapped to Odoo priority. |
| Equipment | Optional mapping from an alarm source to a `maintenance.equipment` record. |
| Alarm cleared | Posts a follow-up message on the request. |

## What it does not do

- **One direction only.** The module receives. It never writes back, sends
  commands, or opens a connection to the monitored installation.
- It creates no Odoo object other than `maintenance.request` and its own small
  mapping table.
- It does not configure alarm rules, thresholds or devices — those stay in
  KORELDA.
- It never closes a maintenance request on its own. When an alarm clears the
  module says so in a message; a person decides when the work is done.

## Requirements

- Odoo **18.0**, Community or Enterprise, **self-hosted**. Odoo Online/SaaS
  cannot install custom modules.
- Standard `maintenance` and `mail` modules (both shipped with Odoo).
- The Odoo instance must be reachable over **HTTPS** from the KORELDA
  installation.

## Installation

1. Copy `korelda_bridge/` into your Odoo addons path.
2. Restart Odoo, update the apps list, and install
   **KORELDA Bridge — Alarm to Maintenance**.
3. Open *Settings → Maintenance → KORELDA Bridge* and set the **shared
   secret**. Use a long random value.
4. On the KORELDA side, add this Odoo instance as a webhook target and store
   the same secret there.

The shared secret is what authenticates every delivery. Anyone who holds it
can open maintenance requests in your database — treat it like a password,
and use a different one for every Odoo instance.

## Configuration

Everything lives in *Settings → Maintenance → KORELDA Bridge*:

| Setting | Meaning |
|---|---|
| **Shared secret** | Authenticates every delivery. Same value on both sides. |
| **Default equipment** | Used when a rule is not mapped. May be left empty. |
| **Rule mapping** | *Maintenance → Configuration → KORELDA Rule Mapping*. Maps `rule.id` to a piece of equipment. |

There is deliberately **no alarm configuration here**. Rules, thresholds and
devices are defined in KORELDA and stay there; duplicating them in Odoo would
give you two sources of truth that drift apart.

A rule you have not mapped is not a failure: the request is opened anyway and
flagged *equipment not mapped*, so the alarm is never lost while the mapping
is still missing.

## Deployment notes

**The endpoint is unauthenticated by design.** It is a machine-to-machine
route (`auth="none"`); the signature — not an Odoo login — is what proves the
delivery is genuine. Two consequences:

1. **Database selection.** The sender is not a browser and carries no session
   cookie, so Odoo cannot pick a database from the session. Run either a
   single-database instance or set `--db-filter` so the hostname resolves to
   exactly one database. On a multi-database instance without a filter the
   request cannot be routed and will fail.
2. **Put it behind HTTPS.** Terminate TLS at your reverse proxy. The body
   carries plant data and the signature is replayable within its window, so
   it should never travel in clear text.

**Workers.** Replay protection stores seen signatures in a database table, not
in process memory, so it works with any number of Odoo workers.

**Retries.** KORELDA does not retry, and does not follow redirects. Answer
quickly (`2xx`) and do the slow work afterwards; a redirect is treated as a
failure.

## What the sender must guarantee

The full receiver contract is published by KORELDA. In short, each delivery:

- is a `POST` with the raw JSON body the signature was computed over;
- carries `X-BMS-Signature: sha256=<hex>`, an HMAC-SHA256 over those exact
  bytes;
- carries a `ts` field. Deliveries older or newer than **5 minutes** are
  rejected, and a signature that has already been processed is accepted but
  **not** processed again (idempotent replay handling).

Both checks are required: the time window alone would let an intercepted
request be replayed inside it, and the seen-signature cache alone would let an
old body become valid again once the cache expired.

Alarm bodies come in two shapes — a lean one (event, rule, severity, active,
ts) and a richer one that also carries the subject, message, inputs and
thresholds. The module accepts both; the lean shape is the default on the
KORELDA side, and which one you receive is the plant operator's decision.

Events other than `rule_alarm` (test deliveries, notifications, scheduled
reports) are answered with `200` and ignored — a valid signature is never
answered with an error just because the module has nothing to do.

## Licence

LGPL-3. The LGPL adds permissions on top of the GPL, so both texts apply —
see [`LICENSE`](../LICENSE) and [`COPYING`](../COPYING) at the repository
root.
