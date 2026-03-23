"""Settings-Service: Zentrale Verwaltung von Systemeinstellungen mit Cache"""
import json
from datetime import datetime
from models import db, SystemSetting

# Einfacher In-Memory-Cache
_cache = {}
_cache_timestamp = {}
CACHE_TTL_SECONDS = 300  # 5 Minuten


def _cache_key(org_id, key):
    """Erzeugt einen eindeutigen Cache-Key"""
    return f'{org_id}:{key}'


def _is_cache_valid(cache_key):
    """Prueft ob ein Cache-Eintrag noch gueltig ist"""
    if cache_key not in _cache_timestamp:
        return False
    elapsed = (datetime.utcnow() - _cache_timestamp[cache_key]).total_seconds()
    return elapsed < CACHE_TTL_SECONDS


def invalidate_cache(org_id=None, key=None):
    """Cache invalidieren (komplett oder gezielt)"""
    if org_id is None:
        _cache.clear()
        _cache_timestamp.clear()
    elif key is not None:
        ck = _cache_key(org_id, key)
        _cache.pop(ck, None)
        _cache_timestamp.pop(ck, None)
    else:
        # Alle Keys einer Organisation loeschen
        keys_to_remove = [k for k in _cache if k.startswith(f'{org_id}:')]
        for k in keys_to_remove:
            _cache.pop(k, None)
            _cache_timestamp.pop(k, None)


def get_setting(org_id, key, default=None):
    """Holt eine Einstellung aus der Datenbank (mit Cache)"""
    ck = _cache_key(org_id, key)

    if _is_cache_valid(ck):
        return _cache[ck]

    setting = SystemSetting.query.filter_by(
        organization_id=org_id, key=key
    ).first()

    if not setting:
        return default

    # Wert je nach Typ konvertieren
    value = _convert_value(setting.value, setting.value_type)

    # In Cache speichern
    _cache[ck] = value
    _cache_timestamp[ck] = datetime.utcnow()

    return value


def set_setting(org_id, key, value, value_type='string', category=None):
    """Speichert eine Einstellung in der Datenbank"""
    setting = SystemSetting.query.filter_by(
        organization_id=org_id, key=key
    ).first()

    # Wert fuer DB vorbereiten
    db_value = _prepare_value(value, value_type)

    if setting:
        setting.value = db_value
        setting.value_type = value_type
        if category:
            setting.category = category
    else:
        setting = SystemSetting(
            organization_id=org_id,
            key=key,
            value=db_value,
            value_type=value_type,
            category=category
        )
        db.session.add(setting)

    db.session.commit()

    # Cache aktualisieren
    ck = _cache_key(org_id, key)
    converted = _convert_value(db_value, value_type)
    _cache[ck] = converted
    _cache_timestamp[ck] = datetime.utcnow()

    return converted


def get_settings_by_category(org_id, category):
    """Alle Einstellungen einer Kategorie als Dict"""
    settings = SystemSetting.query.filter_by(
        organization_id=org_id, category=category
    ).all()

    result = {}
    for s in settings:
        result[s.key] = _convert_value(s.value, s.value_type)

    return result


def _convert_value(value, value_type):
    """Konvertiert einen DB-Wert in den richtigen Python-Typ"""
    if value is None:
        return None

    if value_type == 'integer':
        try:
            return int(value)
        except (ValueError, TypeError):
            return 0
    elif value_type == 'float':
        try:
            return float(value)
        except (ValueError, TypeError):
            return 0.0
    elif value_type == 'boolean':
        return value.lower() in ('true', '1', 'yes', 'on')
    elif value_type == 'json':
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}

    return value


def _prepare_value(value, value_type):
    """Bereitet einen Python-Wert fuer die DB vor"""
    if value is None:
        return None

    if value_type == 'boolean':
        return 'true' if value else 'false'
    elif value_type == 'json':
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=False)
        return value
    elif value_type in ('integer', 'float'):
        return str(value)

    return str(value)
