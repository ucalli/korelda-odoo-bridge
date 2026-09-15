"""Uç noktanın GERÇEK HTTP yolu — ``HttpCase``.

⚠️ Neden ayrı bir sınıf: ``TransactionCase`` model metodunu **kimliği belli
bir kullanıcıyla** çağırır, oysa uç nokta ``auth="none"`` altında
**kullanıcısız** bir ortamda koşar. İkisi aynı şey değildir ve fark gerçek
bir kusur doğurdu: kullanıcısız ortamda ``env.company`` boş kalıyor ve
``maintenance.request.company_id`` NOT NULL kısıtına takılıyordu. Model
testleri yeşilken uç nokta 400 dönüyordu.

Guard kusurun MEKANİZMASINI modellemelidir: buradaki testler isteği gerçekten
HTTP üzerinden atar, yani route + auth + ortam bağı dahil her şeyi geçer.
"""

import hashlib
import hmac
import json
import time

from odoo.tests import HttpCase, tagged

SECRET = "http-case-secret-not-a-real-one"


@tagged("post_install", "-at_install")
class TestKoreldaWebhookHttp(HttpCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.env["ir.config_parameter"].sudo().set_param(
            "korelda_bridge.webhook_secret", SECRET
        )
        cls.env["ir.config_parameter"].sudo().set_param(
            "korelda_bridge.default_equipment_id", ""
        )
        cls.Request = cls.env["maintenance.request"]

    # ── yardımcılar ─────────────────────────────────────────────────────

    def _govde(self, **kw):
        """Sözleşme §5.1 yalın alarm gövdesi, gönderenin serileştirmesiyle."""
        payload = {
            "event": "rule_alarm",
            "rule": {"id": "http-r1", "name": "HTTP testi"},
            "severity": "high",
            "active": True,
            "ts": time.time(),
        }
        payload.update(kw)
        return json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")

    def _imza(self, ham, secret=SECRET):
        return "sha256=" + hmac.new(
            secret.encode("utf-8"), ham, hashlib.sha256
        ).hexdigest()

    def _gonder(self, ham, imza=None):
        if imza is None:
            imza = self._imza(ham)
        return self.url_open(
            "/korelda/webhook",
            data=ham,
            headers={
                "Content-Type": "application/json",
                "X-BMS-Signature": imza,
            },
            timeout=30,
        )

    # ── testler ─────────────────────────────────────────────────────────

    def test_imzali_alarm_talep_acar(self):
        """🔴 Regresyon: kullanıcısız ortamda `company_id` NULL kalıyordu."""
        yanit = self._gonder(self._govde())
        self.assertEqual(yanit.status_code, 200, yanit.text)
        govde = yanit.json()
        self.assertTrue(govde["handled"], govde)

        talep = self.Request.browse(govde["request_id"])
        self.assertTrue(talep.exists())
        self.assertTrue(talep.company_id, "company_id DOLU olmalı")
        self.assertEqual(talep.korelda_rule_id, "http-r1")
        self.assertEqual(talep.priority, "3")

    def test_gecersiz_imza_401_ve_kayit_ACMAZ(self):
        ham = self._govde(rule={"id": "http-bad", "name": "X"})
        yanit = self._gonder(ham, imza=self._imza(ham, secret="yanlis"))
        self.assertEqual(yanit.status_code, 401)
        self.assertEqual(
            self.Request.search_count([("korelda_rule_id", "=", "http-bad")]), 0
        )

    def test_eksik_imza_basligi_401(self):
        yanit = self._gonder(self._govde(), imza="")
        self.assertEqual(yanit.status_code, 401)

    def test_oneksiz_imza_401(self):
        ham = self._govde()
        yanit = self._gonder(ham, imza=self._imza(ham)[len("sha256="):])
        self.assertEqual(yanit.status_code, 401)

    def test_eski_ts_401_ve_kayit_ACMAZ(self):
        ham = self._govde(
            rule={"id": "http-stale", "name": "X"}, ts=time.time() - 400
        )
        self.assertEqual(self._gonder(ham).status_code, 401)
        self.assertEqual(
            self.Request.search_count([("korelda_rule_id", "=", "http-stale")]), 0
        )

    def test_replay_200_idempotent_ve_ISLENMEZ(self):
        ham = self._govde(rule={"id": "http-replay", "name": "X"})
        imza = self._imza(ham)

        ilk = self._gonder(ham, imza=imza)
        self.assertEqual(ilk.status_code, 200)
        self.assertTrue(ilk.json()["handled"])

        tekrar = self._gonder(ham, imza=imza)
        self.assertEqual(tekrar.status_code, 200, "sözleşme §4/2: idempotent kabul")
        self.assertFalse(tekrar.json()["handled"])
        self.assertEqual(tekrar.json()["reason"], "duplicate")
        self.assertEqual(
            self.Request.search_count([("korelda_rule_id", "=", "http-replay")]), 1
        )

    def test_alarm_disi_olaylar_200_handled_false(self):
        for gövde in (
            {"event": "rule_notify", "rule": {"id": "n"}, "ts": time.time()},
            {"event": "rule_test", "rule": {"id": "t"}, "ts": time.time()},
            {"kind": "scheduled_report", "schedule_id": "R1", "ts": time.time()},
        ):
            ham = json.dumps(
                gövde, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
            yanit = self._gonder(ham)
            self.assertEqual(yanit.status_code, 200, gövde)
            self.assertFalse(yanit.json()["handled"], gövde)

    def test_govde_json_degilse_401(self):
        self.assertEqual(self._gonder(b"bu json degil").status_code, 401)

    def test_secret_yapilandirilmamissa_401(self):
        self.env["ir.config_parameter"].sudo().set_param(
            "korelda_bridge.webhook_secret", ""
        )
        try:
            self.assertEqual(self._gonder(self._govde()).status_code, 401)
        finally:
            self.env["ir.config_parameter"].sudo().set_param(
                "korelda_bridge.webhook_secret", SECRET
            )
