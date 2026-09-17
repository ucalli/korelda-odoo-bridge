======================================
KORELDA Bridge -- Alarm to Maintenance
======================================

Technical reference for the Odoo side of the KORELDA alarm webhook.

The module receives **signed webhooks** from a KORELDA installation and opens
a ``maintenance.request`` for each HVAC alarm. It is one-way: it receives,
it never writes back, sends commands or polls.

.. contents::
   :local:
   :depth: 2

Supported versions
==================

=========  ==========================  ==============
Odoo       Edition                     Branch
=========  ==========================  ==============
18.0       Community / Enterprise      ``18.0``
19.0       Community / Enterprise      ``19.0``
=========  ==========================  ==============

* **Self-hosted only** (on-premise or Odoo.sh). Odoo Online/SaaS cannot
  install custom modules.
* Depends on the standard ``maintenance`` and ``mail`` modules.
* The Odoo instance must be reachable over **HTTPS** from the KORELDA
  installation.

Endpoint
========

::

    POST /korelda/webhook

* ``type="http"``, ``auth="none"``, ``csrf=False`` -- a machine-to-machine
  route. There is no Odoo login; the **signature** is what authenticates the
  delivery.
* The body is read as **raw bytes**; the signature is computed over exactly
  those bytes.
* Only ``POST`` is accepted.

Responses
---------

==========  ===========================================================
Status      Body
==========  ===========================================================
``200``     ``{"ok": true, "handled": <bool>, "reason": ..., ...}``
``401``     ``{"ok": false, "error": "<reason>"}``
==========  ===========================================================

Every rejection uses the same status code (``401``); the reason is in the
body only. Possible reasons:

* ``not_configured`` -- no shared secret is set; nothing is accepted.
* ``bad_signature`` -- header missing, malformed or not matching the body.
* ``bad_json`` -- body is not a JSON object.
* ``stale`` -- ``ts`` is missing or outside the freshness window.

A ``200`` with ``handled: false`` is **not** an error. It is returned for a
replayed delivery (``reason: "duplicate"``) and for valid events this module
does not act on (test deliveries, notifications, scheduled reports, unknown
events). The receiver is forward-compatible: an unknown event is acknowledged,
never rejected.

Signature
=========

Each delivery carries::

    X-BMS-Signature: sha256=<hex>

``<hex>`` is ``HMAC-SHA256(secret, raw_body)``, hex-encoded.

* The secret is stored in the system parameter
  ``korelda_bridge.webhook_secret`` and edited from the settings screen.
* The comparison uses ``hmac.compare_digest`` (constant time).
* Never parse and re-serialise the body before verifying -- key order,
  whitespace or Unicode escaping would change and the signature would fail.
* Neither the secret nor the expected signature is ever logged or returned.

Example (placeholder values)::

    body='{"event":"rule_alarm","rule":{"id":"<RULE_ID>"},"severity":"warning","active":true,"ts":<UNIX_TS>}'
    sig=$(printf '%s' "$body" | openssl dgst -sha256 -hmac '<SHARED_SECRET>' -hex | sed 's/^.* //')
    curl -X POST https://<odoo-host>/korelda/webhook \
         -H 'Content-Type: application/json' \
         -H "X-BMS-Signature: sha256=$sig" \
         --data-binary "$body"

Replay protection (receiver behaviour)
======================================

Two checks, both required:

1. **Freshness window -- 300 seconds.** The body must carry a numeric ``ts``
   (Unix seconds). A delivery with ``|now - ts| > 300`` is rejected
   (``stale``). A missing, non-numeric or boolean ``ts`` is treated as stale.
2. **Seen-signature cache.** Every accepted signature is recorded in a
   database table with a unique constraint. A signature that was already
   processed is answered ``200`` with ``handled: false`` and **not**
   processed again (idempotent). Records are kept for four times the window
   and pruned opportunistically.

The window alone would allow a captured request to be replayed inside it; the
cache alone would let an old body become valid again once the cache expired.

The cache lives in the database, not in process memory, so it is correct with
any number of Odoo workers and under concurrent identical deliveries.

Alarm handling
==============

Only ``event: "rule_alarm"`` creates or updates requests. The dedup key is
``rule.id``.

=================================  ==========================================
Situation                          Result
=================================  ==========================================
New alarm, no open request         New ``maintenance.request``
Alarm again, request still open    Comment on the open request (no new one)
``active: false`` (cleared)        Comment on the open request -- **never
                                   closed automatically**
Cleared, no open request           Acknowledged, nothing to do
No ``rule.id``                     New request every time (no dedup)
=================================  ==========================================

An *open* request is one whose stage is not a "done" stage.

Severity -> priority
--------------------

============  ==========  ==================================
Severity      Priority    Notes
============  ==========  ==================================
``info``      0
``low``       1
``warning``   2
``high``      3
``critical``  3           Title prefixed with ``[CRITICAL]`` (translated)
unknown       2           Deliberately not lowered
============  ==========  ==================================

Title
-----

``subject`` if present, otherwise ``KORELDA alarm: <rule name or id>``.

Titles and chatter notes are written in the **installation language** -- the
language of the administrator user -- not the sender's: the sender is a machine
and carries no ``Accept-Language``. The critical prefix is translatable
(e.g. |kritik| in Turkish).

.. |kritik| unicode:: [KR U+0130 T U+0130 K]

Stored data
-----------

On the request: title, priority, equipment, ``korelda_rule_id`` and the
*unmapped* flag. In the chatter: rule name/id, severity and -- when the sender
includes it -- the alarm message. Nothing is sent to third parties.

Both lean bodies (event, rule, severity, active, ts) and richer bodies
(adding subject and message) are accepted.

Installation
============

1. Put ``korelda_bridge/`` on your addons path (or add this repository to it),
   using the branch matching your Odoo version.
2. Restart Odoo, update the apps list and install
   **KORELDA Bridge -- Alarm to Maintenance**.
3. Configure the shared secret (below).
4. On the KORELDA side, add ``https://<odoo-host>/korelda/webhook`` as a
   webhook target with the same secret.

Deployment notes
----------------

* **Database selection.** The sender has no session cookie, so Odoo cannot
  pick a database from the session. Run a single-database instance, or set
  ``--db-filter`` so the hostname resolves to exactly one database.
* **HTTPS.** Terminate TLS at your reverse proxy; the body must never travel
  in clear text.
* **Redirects and retries.** The sender does not follow redirects and does
  not retry. Answer quickly; a redirect counts as a failure.

Shared secret
=============

*Settings -> Maintenance -> KORELDA Bridge -> Shared secret*

* Use a long random value, different for every Odoo instance.
* Anyone holding it can open maintenance requests in your database -- treat it
  like a password.
* While it is empty, every delivery is rejected (``not_configured``).

Equipment mapping
=================

*Maintenance -> Configuration -> KORELDA Rule Mapping*
(also linked from the settings block; requires the *Equipment Manager* group).

Resolution order for a new request:

1. A mapping row whose rule id matches ``rule.id``.
2. The **default equipment** (*Settings -> Maintenance -> KORELDA Bridge*),
   useful for single-site setups.
3. None -- the request is still opened, flagged **equipment not mapped**, and
   a chatter note explains what to set. No alarm is lost.

Alarm rules, thresholds and devices are **not** configured in Odoo; they stay
in KORELDA.

Support
=======

* Support: support@korelda.ai
* Website: https://www.korelda.ai
* Licence: LGPL-3
