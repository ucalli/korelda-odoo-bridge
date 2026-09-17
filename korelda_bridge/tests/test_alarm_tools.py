"""Alarm → talep alanı kararları — birim testleri (Odoo GEREKMEZ).

Kayıt işlemlerinin kendisi (create / message_post / dedup araması) Odoo
ister; onlar ``test_alarm_flow.py`` içinde ``TransactionCase`` olarak
duruyor ve kurulum smoke'unda (FAZ 1.4) koşar. Burada yalnız saf kararlar.
"""

import pathlib
import unittest

try:  # Odoo içinde
    from odoo.addons.korelda_bridge.tools import alarm as al
except ImportError:  # Odoo dışında (yerel birim koşusu)
    import importlib.util

    _p = pathlib.Path(__file__).resolve().parents[1] / "tools" / "alarm.py"
    _spec = importlib.util.spec_from_file_location("_korelda_al", str(_p))
    al = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(al)


class OncelikTest(unittest.TestCase):
    """K11 — beş önem seviyesi."""

    def test_bes_seviye(self):
        beklenen = {
            "info": "0",
            "low": "1",
            "warning": "2",
            "high": "3",
            "critical": "3",
        }
        for onem, oncelik in beklenen.items():
            self.assertEqual(al.priority_for(onem), oncelik, onem)

    def test_high_ve_critical_ayni_kovada_ama_baslikla_ayrilir(self):
        """Odoo'da dördüncü öncelik yok; ayrım başlıktaki kritik önekinde."""
        self.assertEqual(al.priority_for("high"), al.priority_for("critical"))
        self.assertFalse(al.is_critical("high"))
        self.assertTrue(al.is_critical("critical"))

    def test_buyuk_harf_ve_bosluk_tolere(self):
        self.assertEqual(al.priority_for(" CRITICAL "), "3")
        self.assertTrue(al.is_critical(" Critical "))

    def test_bilinmeyen_onem_dusuk_sayilmaz(self):
        """Tanımadığımız önemi sessizce önemsizleştirmek riski gizlerdi."""
        for deger in ("uydurma", "", None, 3, {}, True):
            self.assertEqual(al.priority_for(deger), al.UNKNOWN_PRIORITY, deger)
        self.assertEqual(al.UNKNOWN_PRIORITY, "2")


class BaslikTest(unittest.TestCase):
    def test_subject_varsa_kullanilir(self):
        p = {"subject": "Donma riski", "rule": {"id": "r1", "name": "Donma"}}
        self.assertEqual(al.request_name(p), "Donma riski")

    def test_subject_yoksa_kural_adi(self):
        p = {"rule": {"id": "r1", "name": "Donma"}}
        self.assertEqual(al.request_name(p), "KORELDA alarm: Donma")

    def test_ad_da_yoksa_kural_id(self):
        p = {"rule": {"id": "r1"}}
        self.assertEqual(al.request_name(p), "KORELDA alarm: r1")

    def test_hicbiri_yoksa_yedek(self):
        self.assertEqual(al.request_name({}), "KORELDA alarm")
        self.assertEqual(al.request_name(None), "KORELDA alarm")

    def test_yalin_govdede_subject_YOK_ama_baslik_uretilir(self):
        """Sözleşme §5.1: yalın gövdede ``subject`` alanı hiç yoktur."""
        yalin = {"event": "rule_alarm", "rule": {"id": "r1", "name": "Donma"},
                 "severity": "high", "active": True, "ts": 1757800000.0}
        self.assertNotIn("subject", yalin)
        self.assertEqual(al.request_name(yalin), "KORELDA alarm: Donma")

    def test_kritik_isareti_onek_URETMEZ(self):
        """Önek çevrilir → saf katman yalnız bayrak döndürür, metin değil."""
        p = {"subject": "Donma riski", "severity": "critical"}
        self.assertEqual(al.request_name(p), "Donma riski")
        self.assertEqual(al.request_title(p), ("Donma riski", True))
        self.assertFalse(hasattr(al, "CRITICAL_PREFIX"))

    def test_kritik_isareti_yalniz_critical(self):
        for onem in ("high", "warning", "low", "info", None, "uydurma", 3):
            p = {"subject": "X", "severity": onem}
            self.assertEqual(al.request_title(p), ("X", False), onem)

    def test_kritik_isareti_buyuk_harf_ve_bosluk(self):
        p = {"rule": {"name": "Donma"}, "severity": " CRITICAL "}
        self.assertEqual(al.request_title(p), ("KORELDA alarm: Donma", True))

    def test_request_title_bos_govde(self):
        self.assertEqual(al.request_title(None), ("KORELDA alarm", False))
        self.assertEqual(al.request_title({}), ("KORELDA alarm", False))

    def test_bos_subject_kural_adina_duser(self):
        p = {"subject": "   ", "rule": {"name": "Donma"}}
        self.assertEqual(al.request_name(p), "KORELDA alarm: Donma")

    def test_subject_string_degilse_yok_sayilir(self):
        p = {"subject": 42, "rule": {"name": "Donma"}}
        self.assertEqual(al.request_name(p), "KORELDA alarm: Donma")


class AnahtarTest(unittest.TestCase):
    """K13 — dedup anahtarı kuralın ``id``'si."""

    def test_kural_id(self):
        self.assertEqual(al.rule_key({"rule": {"id": "r1", "name": "D"}}), "r1")

    def test_sayisal_id_metne_cevrilir(self):
        self.assertEqual(al.rule_key({"rule": {"id": 7}}), "7")

    def test_bosluk_kirpilir(self):
        self.assertEqual(al.rule_key({"rule": {"id": "  r1 "}}), "r1")

    def test_anahtarsiz_govde_bos_doner(self):
        """Boş anahtar = dedup YOK. Anahtarsız gövdeleri tek kovada
        birleştirmek farklı kuralları birbirinin tekrarı sayardı."""
        for p in ({}, {"rule": None}, {"rule": {}}, {"rule": {"name": "D"}},
                  {"rule": "r1"}, None):
            self.assertEqual(al.rule_key(p), "", p)

    def test_etiket_ad_yoksa_id(self):
        self.assertEqual(al.rule_label({"rule": {"id": "r1", "name": "D"}}), "D")
        self.assertEqual(al.rule_label({"rule": {"id": "r1"}}), "r1")
        self.assertEqual(al.rule_label({}), "")


class TemizlenmeTest(unittest.TestCase):
    """K12 — ``active: false``."""

    def test_acik_false_temizlenme(self):
        self.assertTrue(al.is_cleared({"active": False}))

    def test_true_temizlenme_degil(self):
        self.assertFalse(al.is_cleared({"active": True}))

    def test_eksik_active_temizlenme_DEGIL(self):
        """Alanı olmayan gövdeyi 'kapandı' saymak sessiz bir kayıp olurdu."""
        self.assertFalse(al.is_cleared({}))
        self.assertFalse(al.is_cleared(None))

    def test_yanlis_tipler_temizlenme_degil(self):
        for deger in (0, "", "false", None, [], {}):
            self.assertFalse(al.is_cleared({"active": deger}), deger)


if __name__ == "__main__":
    unittest.main()
