"""Alarm → bakım talebi akışı — Odoo ``TransactionCase``.

⚠️ Bu dosya **kurulu bir Odoo** ister (veritabanı, `maintenance` modülü).
Odoo test koşucusuyla çalışır:

    odoo -d <db> -i korelda_bridge --test-enable --stop-after-init

Saf karar mantığının testleri ``test_alarm_tools.py``dedir ve Odoo olmadan
koşar; burada yalnız kayıt işlemleri sınanır (create · dedup araması ·
message_post · eşlenmemiş işareti · kapatmama).
"""

from odoo.tests import TransactionCase, tagged


@tagged("post_install", "-at_install")
class TestKoreldaAlarmFlow(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Request = cls.env["maintenance.request"]
        cls.Mapping = cls.env["korelda.mapping"]
        cls.Equipment = cls.env["maintenance.equipment"]
        cls.ekipman = cls.Equipment.create({"name": "AHU-TEST-1"})
        cls.yedek = cls.Equipment.create({"name": "AHU-TEST-VARSAYILAN"})

    # ── yardımcılar ─────────────────────────────────────────────────────

    def _govde(self, **kw):
        """Sözleşme §5.1 yalın alarm gövdesi; `kw` ile üzerine yazılır."""
        govde = {
            "event": "rule_alarm",
            "rule": {"id": "r-test-1", "name": "Donma riski"},
            "severity": "high",
            "active": True,
            "ts": 1757800000.0,
        }
        govde.update(kw)
        return govde

    def _talep(self, request_id):
        return self.Request.browse(request_id)

    def _param(self, deger):
        self.env["ir.config_parameter"].sudo().set_param(
            "korelda_bridge.default_equipment_id", deger
        )

    # ── kayıt açma ──────────────────────────────────────────────────────

    def test_alarm_talep_acar(self):
        self.Mapping.create(
            {"rule_id": "r-test-1", "equipment_id": self.ekipman.id}
        )
        sonuc = self.Request.korelda_process_alarm(self._govde())
        self.assertTrue(sonuc["handled"])
        self.assertEqual(sonuc["reason"], "created")
        talep = self._talep(sonuc["request_id"])
        self.assertEqual(talep.korelda_rule_id, "r-test-1")
        self.assertEqual(talep.equipment_id, self.ekipman)
        self.assertFalse(talep.korelda_unmapped)
        self.assertEqual(talep.name, "KORELDA alarm: Donma riski")

    def test_subject_baslik_olur(self):
        sonuc = self.Request.korelda_process_alarm(
            self._govde(subject="Besleme sıcaklığı düşük")
        )
        self.assertEqual(
            self._talep(sonuc["request_id"]).name, "Besleme sıcaklığı düşük"
        )

    def test_oncelik_bes_seviye(self):
        """K11 — her önem kendi kovasına; `critical` ayrıca `[CRITICAL]`."""
        beklenen = [
            ("info", "0", False),
            ("low", "1", False),
            ("warning", "2", False),
            ("high", "3", False),
            ("critical", "3", True),
        ]
        for i, (onem, oncelik, kritik) in enumerate(beklenen):
            sonuc = self.Request.korelda_process_alarm(
                self._govde(
                    rule={"id": f"r-onem-{i}", "name": "K"}, severity=onem
                )
            )
            talep = self._talep(sonuc["request_id"])
            self.assertEqual(talep.priority, oncelik, onem)
            self.assertEqual(talep.name.startswith("[CRITICAL] "), kritik, onem)

    def test_kritik_oneki_cevrilir(self):
        """K11 — önek Odoo çeviri katmanından: EN `[CRITICAL]`, TR `[KRİTİK]`."""
        self.env["res.lang"]._activate_lang("tr_TR")
        govde = dict(severity="critical", subject="Donma riski")
        en = self.Request.with_context(lang="en_US").korelda_process_alarm(
            self._govde(rule={"id": "r-dil-en", "name": "K"}, **govde)
        )
        tr = self.Request.with_context(lang="tr_TR").korelda_process_alarm(
            self._govde(rule={"id": "r-dil-tr", "name": "K"}, **govde)
        )
        self.assertEqual(self._talep(en["request_id"]).name, "[CRITICAL] Donma riski")
        self.assertEqual(self._talep(tr["request_id"]).name, "[KRİTİK] Donma riski")

    # ── eşleme (K10) ────────────────────────────────────────────────────

    def test_eslesme_yoksa_varsayilan_ekipman(self):
        self._param(str(self.yedek.id))
        sonuc = self.Request.korelda_process_alarm(
            self._govde(rule={"id": "r-eslemesiz", "name": "K"})
        )
        talep = self._talep(sonuc["request_id"])
        self.assertEqual(talep.equipment_id, self.yedek)
        self.assertFalse(talep.korelda_unmapped)

    def test_eslesme_de_varsayilan_da_yoksa_YINE_ACILIR(self):
        """K10 — sessiz kayıp YASAK: ekipman bulunamasa da talep açılır."""
        self._param("")
        sonuc = self.Request.korelda_process_alarm(
            self._govde(rule={"id": "r-hicbiri", "name": "K"})
        )
        talep = self._talep(sonuc["request_id"])
        self.assertTrue(sonuc["handled"])
        self.assertFalse(talep.equipment_id)
        self.assertTrue(talep.korelda_unmapped, "eşlenmemiş işareti konmalı")
        govdeler = " ".join(talep.message_ids.mapped("body"))
        self.assertIn("No equipment is mapped", govdeler)

    def test_inputs_ref_ten_ekipman_CIKARILMAZ(self):
        """K10 — gönderenin iç adresleme biçimi eşleme kaynağı değildir."""
        self._param("")
        sonuc = self.Request.korelda_process_alarm(
            self._govde(
                rule={"id": "r-inputs", "name": "K"},
                inputs=[{"ref": f"equipment/{self.ekipman.name}", "value": 1}],
            )
        )
        self.assertTrue(self._talep(sonuc["request_id"]).korelda_unmapped)

    def test_devre_disi_esleme_kullanilmaz(self):
        self._param("")
        self.Mapping.create(
            {
                "rule_id": "r-kapali",
                "equipment_id": self.ekipman.id,
                "active": False,
            }
        )
        sonuc = self.Request.korelda_process_alarm(
            self._govde(rule={"id": "r-kapali", "name": "K"})
        )
        self.assertTrue(self._talep(sonuc["request_id"]).korelda_unmapped)

    # ── dedup (K13) ─────────────────────────────────────────────────────

    def test_acik_talep_varsa_yeni_ACILMAZ_yorum_duser(self):
        ilk = self.Request.korelda_process_alarm(self._govde())
        onceki_mesaj = len(self._talep(ilk["request_id"]).message_ids)

        ikinci = self.Request.korelda_process_alarm(self._govde())
        self.assertEqual(ikinci["request_id"], ilk["request_id"])
        self.assertEqual(ikinci["reason"], "duplicate_comment")
        self.assertEqual(
            self.Request.search_count([("korelda_rule_id", "=", "r-test-1")]), 1
        )
        talep = self._talep(ilk["request_id"])
        self.assertGreater(len(talep.message_ids), onceki_mesaj)
        self.assertIn("reported again", " ".join(talep.message_ids.mapped("body")))

    def test_kapali_talep_dedup_ETMEZ(self):
        """Talep bitmişse aynı kuralın yeni alarmı YENİ talep açmalı."""
        ilk = self.Request.korelda_process_alarm(self._govde())
        bitti = self.env["maintenance.stage"].search([("done", "=", True)], limit=1)
        if not bitti:
            bitti = self.env["maintenance.stage"].create(
                {"name": "Bitti (test)", "done": True}
            )
        self._talep(ilk["request_id"]).stage_id = bitti

        ikinci = self.Request.korelda_process_alarm(self._govde())
        self.assertEqual(ikinci["reason"], "created")
        self.assertNotEqual(ikinci["request_id"], ilk["request_id"])

    def test_anahtarsiz_govde_dedup_EDILMEZ(self):
        a = self.Request.korelda_process_alarm(self._govde(rule={}))
        b = self.Request.korelda_process_alarm(self._govde(rule={}))
        self.assertNotEqual(a["request_id"], b["request_id"])

    # ── alarm temizlendi (K12) ──────────────────────────────────────────

    def test_active_false_talebi_KAPATMAZ_yorum_duser(self):
        ilk = self.Request.korelda_process_alarm(self._govde())
        talep = self._talep(ilk["request_id"])
        asama_once = talep.stage_id

        sonuc = self.Request.korelda_process_alarm(self._govde(active=False))
        self.assertEqual(sonuc["reason"], "cleared_comment")
        self.assertEqual(sonuc["request_id"], ilk["request_id"])
        talep.invalidate_recordset()
        self.assertEqual(talep.stage_id, asama_once, "aşama DEĞİŞMEMELİ")
        self.assertFalse(talep.stage_id.done, "talep kapatılmamalı")
        self.assertIn("cleared", " ".join(talep.message_ids.mapped("body")))

    def test_active_false_acik_talep_yoksa_yeni_ACMAZ(self):
        sonuc = self.Request.korelda_process_alarm(
            self._govde(rule={"id": "r-hic-acilmadi", "name": "K"}, active=False)
        )
        self.assertFalse(sonuc["handled"])
        self.assertEqual(sonuc["reason"], "no_open_request")
        self.assertEqual(
            self.Request.search_count(
                [("korelda_rule_id", "=", "r-hic-acilmadi")]
            ),
            0,
        )

    # ── eşleme modeli ───────────────────────────────────────────────────

    def test_ayni_kural_icin_iki_esleme_OLAMAZ(self):
        from psycopg2 import IntegrityError

        from odoo.tools import mute_logger

        self.Mapping.create({"rule_id": "r-tek", "equipment_id": self.ekipman.id})
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                self.Mapping.create(
                    {"rule_id": "r-tek", "equipment_id": self.yedek.id}
                )

    def test_gorulmus_imza_kisiti_GERCEKTEN_var(self):
        """🔴 Replay korumasının YARIŞ backstop'u veritabanında olmalı.

        Odoo 19'da `_sql_constraints` sessizce yok sayılıyor; kısıt
        oluşmazsa eşzamanlı iki özdeş istek ikisi de işlenebilirdi. Bu
        kaybın görünür bir belirtisi YOKTU — bu yüzden kısıtın varlığı
        doğrudan sınanır.
        """
        from psycopg2 import IntegrityError

        from odoo.tools import mute_logger

        Seen = self.env["korelda.webhook.seen"]
        Seen.create({"signature": "sha256=kisit-testi"})
        with self.assertRaises(IntegrityError), mute_logger("odoo.sql_db"):
            with self.cr.savepoint():
                Seen.create({"signature": "sha256=kisit-testi"})
                self.env.flush_all()

    # ── enjeksiyon ──────────────────────────────────────────────────────

    def test_govde_metni_html_olarak_kacirilir(self):
        """Gövde dış girdidir; başlık Odoo sohbetine markup enjekte edemez."""
        sonuc = self.Request.korelda_process_alarm(
            self._govde(
                rule={"id": "r-xss", "name": "<script>alert(1)</script>"}
            )
        )
        talep = self._talep(sonuc["request_id"])
        govdeler = " ".join(talep.message_ids.mapped("body"))
        self.assertNotIn("<script>", govdeler)
        self.assertIn("&lt;script&gt;", govdeler)
