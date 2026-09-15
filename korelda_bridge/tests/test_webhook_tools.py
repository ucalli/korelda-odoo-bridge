"""Webhook doğrulama çekirdeği — birim testleri (Odoo GEREKMEZ).

Odoo test koşucusu bu dosyayı `unittest.TestCase` olarak alır; Odoo'suz
ortamda da `python -m unittest` / `pytest` ile koşar (aşağıdaki iki-yollu
import). Böylece imza/tazelik/sınıflandırma davranışı, kurulu bir Odoo
olmadan da guard altında.

Veritabanına dokunan tek parça (görülmüş-imza deposu) burada değil; onun
davranışı kurulum smoke'unda (FAZ 1.4) sınanır.
"""

import hashlib
import hmac
import pathlib
import re
import unittest

try:  # Odoo içinde
    from odoo.addons.korelda_bridge.tools import webhook as wh
except ImportError:  # Odoo dışında (yerel birim koşusu)
    import importlib.util

    _p = pathlib.Path(__file__).resolve().parents[1] / "tools" / "webhook.py"
    _spec = importlib.util.spec_from_file_location("_korelda_wh", str(_p))
    wh = importlib.util.module_from_spec(_spec)
    _spec.loader.exec_module(wh)

SECRET = "test-secret-not-a-real-one"
BODY = b'{"active":true,"event":"rule_alarm","rule":{"id":"r1","name":"D"},"severity":"critical","ts":1757800000.0}'


def _imzala(secret=SECRET, body=BODY):
    return "sha256=" + hmac.new(
        secret.encode("utf-8"), body, hashlib.sha256
    ).hexdigest()


class ImzaTest(unittest.TestCase):
    def test_gecerli_imza_kabul(self):
        self.assertTrue(wh.signature_matches(SECRET, BODY, _imzala()))

    def test_gecersiz_imza_red(self):
        bozuk = _imzala(secret="baska-secret")
        self.assertFalse(wh.signature_matches(SECRET, BODY, bozuk))

    def test_eksik_baslik_red(self):
        self.assertFalse(wh.signature_matches(SECRET, BODY, ""))
        self.assertFalse(wh.signature_matches(SECRET, BODY, None))

    def test_onek_yoksa_red(self):
        ham = _imzala()[len("sha256="):]
        self.assertFalse(wh.signature_matches(SECRET, BODY, ham))

    def test_secret_yoksa_red(self):
        self.assertFalse(wh.signature_matches("", BODY, _imzala()))

    def test_govde_tek_bayt_degisince_red(self):
        self.assertFalse(wh.signature_matches(SECRET, BODY + b" ", _imzala()))

    def test_imza_ham_baytlar_uzerinde(self):
        """Sözleşme §3: alıcı gövdeyi parse edip YENİDEN ÜRETMEMELİ.

        Aynı JSON'un boşluklu yazımı farklı baytlardır ve imza tutmaz —
        bu test o sözleşmeyi kilitler.
        """
        import json

        yeniden = json.dumps(json.loads(BODY.decode())).encode()
        self.assertNotEqual(yeniden, BODY)
        self.assertFalse(wh.signature_matches(SECRET, yeniden, _imzala()))


class TazelikTest(unittest.TestCase):
    NOW = 1757800000.0

    def test_taze_kabul(self):
        self.assertTrue(wh.timestamp_is_fresh(self.NOW, self.NOW))
        self.assertTrue(wh.timestamp_is_fresh(self.NOW - 299, self.NOW))
        self.assertTrue(wh.timestamp_is_fresh(self.NOW + 299, self.NOW))

    def test_sinir_tam_300_kabul(self):
        self.assertTrue(wh.timestamp_is_fresh(self.NOW - 300, self.NOW))

    def test_eski_red(self):
        self.assertFalse(wh.timestamp_is_fresh(self.NOW - 301, self.NOW))

    def test_gelecek_red(self):
        """Saati ileri alınmış bir gönderici de pencereyi genişletemez."""
        self.assertFalse(wh.timestamp_is_fresh(self.NOW + 301, self.NOW))

    def test_eksik_ts_red(self):
        self.assertFalse(wh.timestamp_is_fresh(None, self.NOW))

    def test_sayi_olmayan_ts_red(self):
        self.assertFalse(wh.timestamp_is_fresh("1757800000", self.NOW))
        self.assertFalse(wh.timestamp_is_fresh({}, self.NOW))

    def test_bool_ts_red(self):
        """`bool` Python'da `int` alt türü; `True` sessizce 1 (1970) sayılırdı."""
        self.assertFalse(wh.timestamp_is_fresh(True, self.NOW))
        self.assertFalse(wh.timestamp_is_fresh(False, self.NOW))


class SiniflandirmaTest(unittest.TestCase):
    def test_alarm(self):
        self.assertEqual(wh.classify({"event": "rule_alarm"})[0], "alarm")

    def test_yok_sayilan_kural_olaylari(self):
        for e in ("rule_notify", "rule_test"):
            self.assertEqual(wh.classify({"event": e})[0], "ignored", e)

    def test_zamanli_rapor_event_anahtari_YOK(self):
        """Sözleşme §5.3: rapor gövdesinde `event` yoktur, `kind` vardır."""
        p = {"kind": "scheduled_report", "schedule_id": "R1", "type": "health"}
        self.assertEqual(wh.classify(p)[0], "report")

    def test_bilinmeyen_olay_hata_degil(self):
        """İleri uyum: gönderen yeni olay tipi ekleyebilir."""
        self.assertEqual(wh.classify({"event": "rule_gelecekte"})[0], "unknown")
        self.assertEqual(wh.classify({})[0], "unknown")
        self.assertEqual(wh.classify(None)[0], "unknown")

    def test_yalin_ve_zengin_govde_ayni_siniflanir(self):
        """Gövde seviyesi (yalın/zengin) yönlendirmeyi DEĞİŞTİRMEZ."""
        yalin = {"event": "rule_alarm", "severity": "high"}
        zengin = dict(yalin, subject="K", message="m", inputs=[], thresholds=[])
        self.assertEqual(wh.classify(yalin)[0], wh.classify(zengin)[0])


class SabitZamanliKarsilastirmaGuard(unittest.TestCase):
    """Statik guard: imza `==` ile karşılaştırılmıyor (sözleşme §3)."""

    def _kaynaklar(self):
        kok = pathlib.Path(__file__).resolve().parents[1]
        return [p for p in kok.rglob("*.py") if "tests" not in p.parts]

    def test_compare_digest_kullaniliyor(self):
        metin = (pathlib.Path(__file__).resolve().parents[1]
                 / "tools" / "webhook.py").read_text(encoding="utf-8")
        self.assertIn("hmac.compare_digest", metin)

    def test_imza_esitlik_operatoruyle_karsilastirilmiyor(self):
        desen = re.compile(
            r"(signature|imza|sig|digest|hexdigest\(\))\s*(==|!=)", re.I)
        for p in self._kaynaklar():
            for i, satir in enumerate(
                    p.read_text(encoding="utf-8").splitlines(), 1):
                self.assertIsNone(
                    desen.search(satir),
                    f"{p.name}:{i} imza '==' ile karşılaştırılıyor: {satir!r}")


class SozlesmeSabitleriTest(unittest.TestCase):
    """Sabitler yayımlanmış sözleşmeyle aynı kalmalı."""

    def test_baslik_ve_onek(self):
        self.assertEqual(wh.SIGNATURE_HEADER, "X-BMS-Signature")
        self.assertEqual(wh.SIGNATURE_PREFIX, "sha256=")

    def test_replay_penceresi_300(self):
        self.assertEqual(wh.REPLAY_WINDOW_SEC, 300)

    def test_olay_adlari(self):
        self.assertEqual(wh.ALARM_EVENT, "rule_alarm")
        self.assertEqual(wh.REPORT_KIND, "scheduled_report")


if __name__ == "__main__":
    unittest.main()
