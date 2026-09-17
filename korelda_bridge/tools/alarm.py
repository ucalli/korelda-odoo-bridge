"""Alarm gövdesi → bakım talebi alanları. Saf Python, Odoo bağımlılığı YOK.

Kayıt açma Odoo tarafında (``models/maintenance_request.py``); burada yalnız
gövdeden türetilen **kararlar** var, böylece Odoo kurulu olmadan da sınanır.
"""

#: Önem → Odoo ``maintenance.request.priority`` (seçim kümesi 0..3).
#: ``high`` ve ``critical`` aynı en yüksek kovaya düşer — Odoo'da dördüncü bir
#: seviye yok; ayrım başlıktaki kritik öneki ile korunur (öneki model katmanı
#: çeviriyle ekler — bkz. ``request_title``).
SEVERITY_PRIORITY = {
    "info": "0",
    "low": "1",
    "warning": "2",
    "high": "3",
    "critical": "3",
}

#: Bilinmeyen/eksik önem için kova. **Bilerek "düşük" DEĞİL**: tanımadığımız
#: bir önemi sessizce önemsizleştirmek, gerçek riski gizlerdi.
UNKNOWN_PRIORITY = "2"

CRITICAL_SEVERITY = "critical"


def priority_for(severity):
    """Önem → Odoo önceliği. Tanınmayan/eksik önem ``UNKNOWN_PRIORITY``."""
    if not isinstance(severity, str):
        return UNKNOWN_PRIORITY
    return SEVERITY_PRIORITY.get(severity.strip().lower(), UNKNOWN_PRIORITY)


def is_critical(severity):
    return isinstance(severity, str) and severity.strip().lower() == CRITICAL_SEVERITY


def rule_key(payload):
    """Dedup ve izleme anahtarı: kuralın ``id``'si (K13).

    Boş dönerse **dedup yapılamaz** — çağıran her seferinde yeni talep açar.
    Bu bilinçli: anahtarsız gövdeleri tek bir kovada birleştirmek, farklı
    kuralları birbirinin tekrarı sayardı.
    """
    rule = (payload or {}).get("rule")
    if not isinstance(rule, dict):
        return ""
    return str(rule.get("id") or "").strip()


def rule_label(payload):
    """İnsan-okur kural adı; yoksa id; o da yoksa boş."""
    rule = (payload or {}).get("rule")
    if not isinstance(rule, dict):
        return ""
    return str(rule.get("name") or rule.get("id") or "").strip()


def request_name(payload, fallback="KORELDA alarm"):
    """Bakım talebinin başlığı.

    Sıra: gövdedeki ``subject`` (yalnız zengin gövdede var) → kural adı →
    kural id'si → sabit yedek.

    Kritik öneki burada **eklenmez**: önek kullanıcıya görünen bir metindir ve
    çevrilmesi gerekir; çeviri Odoo katmanının işidir, bu modül Odoo'suz
    kalır. Önek kararı için ``request_title``.
    """
    payload = payload or {}
    subject = payload.get("subject")
    ad = str(subject).strip() if isinstance(subject, str) else ""
    if not ad:
        etiket = rule_label(payload)
        ad = f"{fallback}: {etiket}" if etiket else fallback
    return ad


def request_title(payload, fallback="KORELDA alarm"):
    """``(başlık, kritik_mi)`` — K11.

    Başlık öneksizdir; ``kritik_mi`` doğruysa çağıran (model) çevrilmiş kritik
    önekini başa ekler.
    """
    return (
        request_name(payload, fallback),
        is_critical((payload or {}).get("severity")),
    )


def is_cleared(payload):
    """Alarm temizlendi mi (K12: ``active: false``).

    **Yalnız açık ``False``** temizlenme sayılır. Eksik ``active`` "temizlendi"
    demek değildir — yalın gövdede alan her zaman vardır, ama gelmezse
    alarmı kendiliğimizden kapatılmış saymak sessiz bir kayıp olurdu.
    """
    return (payload or {}).get("active") is False
