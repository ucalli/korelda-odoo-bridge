"""Webhook doğrulama çekirdeği — saf Python, Odoo bağımlılığı YOK.

Odoo'suz test edilebilsin diye ayrı: imza, tazelik penceresi ve olay
sınıflandırması burada; veritabanına dokunan tek şey (görülmüş-imza deposu)
controller tarafında kalır.

Sözleşme: ``docs/dis-entegrasyon-webhook-sozlesmesi.md`` §3-§4 (gönderen
tarafın yayımladığı alıcı sözleşmesi). Buradaki sabitler o belgeden gelir;
değiştirilirse belge de değişmelidir.
"""

import hashlib
import hmac

#: İmza başlığı ve ön eki (sözleşme §3).
SIGNATURE_HEADER = "X-BMS-Signature"
SIGNATURE_PREFIX = "sha256="

#: Tazelik penceresi, saniye (sözleşme §4/1). Görülmüş-imza önbelleğinin
#: TTL'i de en az bu kadar olmalıdır — ikisi birlikte çalışır.
REPLAY_WINDOW_SEC = 300

#: Bakım talebi açan tek olay.
ALARM_EVENT = "rule_alarm"

#: İmzası geçerli ama bu modülün işlemediği kural olayları.
IGNORED_EVENTS = ("rule_notify", "rule_test")

#: Zamanlı rapor gövdesinde ``event`` yoktur; ``kind`` ile gelir (sözleşme §5.3).
REPORT_KIND = "scheduled_report"


def expected_signature(secret, body):
    """``sha256=<hex>`` — gövde **baytları** üzerinden HMAC-SHA256.

    ``body`` bytes olmalıdır. Gelen isteğin JSON'ını parse edip yeniden
    serileştirmek imzayı bozar (anahtar sırası, boşluk, Unicode kaçışı
    değişir) — sözleşme §3 bunu açıkça yasaklıyor.
    """
    mac = hmac.new(secret.encode("utf-8"), body, hashlib.sha256)
    return SIGNATURE_PREFIX + mac.hexdigest()


def signature_matches(secret, body, header_value):
    """Başlıktaki imza gövdeyle tutuyor mu.

    Karşılaştırma **``hmac.compare_digest``** ile yapılır: ``==`` sabit
    zamanlı değildir ve baytları tek tek sızdırır.
    """
    if not secret or not header_value:
        return False
    if not header_value.startswith(SIGNATURE_PREFIX):
        return False
    return hmac.compare_digest(expected_signature(secret, body), header_value)


def timestamp_is_fresh(ts, now, window=REPLAY_WINDOW_SEC):
    """``|now - ts| <= window`` mi (sözleşme §4/1).

    Eksik, sayı olmayan veya ``bool`` bir ``ts`` **taze değildir**: gövdesinde
    zaman damgası taşımayan bir istek tekrar oynatmaya açıktır.
    ``bool`` ayrıca elenir çünkü Python'da ``bool`` bir ``int`` alt türüdür ve
    ``True`` sessizce ``1`` (1970) sayılırdı.
    """
    if isinstance(ts, bool) or not isinstance(ts, (int, float)):
        return False
    return abs(float(now) - float(ts)) <= window


def classify(payload):
    """Gövde → ``(tür, olay_adı)``.

    Türler: ``"alarm"`` (bakım talebi açılır) · ``"ignored"`` (imzası geçerli,
    bu modülün işlemediği kural olayı) · ``"report"`` (zamanlı rapor) ·
    ``"unknown"`` (tanınmayan olay — sözleşme §5 "bilinmeyeni yok say").

    Bilinmeyen olay **hata değildir**: gönderen taraf yeni olay tipleri
    ekleyebilir ve alıcı ileri uyumlu olmalıdır.
    """
    if not isinstance(payload, dict):
        return "unknown", None
    event = payload.get("event")
    if event == ALARM_EVENT:
        return "alarm", event
    if event in IGNORED_EVENTS:
        return "ignored", event
    if event is None and payload.get("kind") == REPORT_KIND:
        return "report", REPORT_KIND
    return "unknown", event
