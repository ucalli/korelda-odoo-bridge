"""Sistem parametresi anahtarları — tek kaynak.

Hem controller (secret okur) hem ayar modeli (secret yazar) hem de kayıt
akışı (varsayılan ekipman) bu adları kullanır. Ortak bir yerde durmazlarsa
model katmanı controller'ı import etmek zorunda kalırdı — ters bağımlılık.
"""

#: Paylaşılan webhook secret'ı. Gönderen (KORELDA) tarafında bu hedef için
#: tanımlanan secret ile aynı değer.
SECRET_PARAM = "korelda_bridge.webhook_secret"

#: Hiçbir eşleme tutmazsa kullanılacak ekipman (opsiyonel).
DEFAULT_EQUIPMENT_PARAM = "korelda_bridge.default_equipment_id"
