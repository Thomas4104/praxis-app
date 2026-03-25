"""
Service fuer die Online-Suche im Schweizer Arzt- und Therapeutenverzeichnis.
Ermoeglicht Lookup via GLN (Global Location Number) und ZSR-Nummer.

Quellen:
- MedReg API (https://www.medreg.admin.ch)
- SASIS Register
"""
import requests
import logging
from flask import current_app

logger = logging.getLogger(__name__)

# MedReg API Base URL
MEDREG_API_URL = 'https://www.medreg.admin.ch/api/glndata'


def lookup_by_gln(gln_number):
    """Sucht einen Leistungserbringer ueber seine GLN-Nummer.

    Args:
        gln_number: 13-stellige GLN (z.B. '7601000000000')

    Returns:
        dict mit Arztdaten oder None bei Fehler
    """
    if not gln_number or len(str(gln_number).strip()) < 10:
        return None, 'GLN-Nummer muss mindestens 10 Stellen haben'

    gln = str(gln_number).strip()

    try:
        response = requests.get(
            f'{MEDREG_API_URL}/{gln}',
            timeout=10,
            headers={'Accept': 'application/json'}
        )

        if response.status_code == 200:
            data = response.json()
            return _parse_medreg_response(data), None
        elif response.status_code == 404:
            return None, f'Kein Eintrag gefunden fuer GLN {gln}'
        else:
            logger.warning(f'MedReg API Fehler: Status {response.status_code}')
            return None, f'API-Fehler: Status {response.status_code}'
    except requests.RequestException as e:
        logger.error(f'MedReg API nicht erreichbar: {e}')
        return None, f'Verbindungsfehler: {str(e)}'


def lookup_by_zsr(zsr_number):
    """Sucht einen Leistungserbringer ueber seine ZSR-Nummer.

    Args:
        zsr_number: ZSR-Nummer (z.B. 'A123456')

    Returns:
        dict mit Arztdaten oder None bei Fehler
    """
    if not zsr_number or len(str(zsr_number).strip()) < 4:
        return None, 'ZSR-Nummer zu kurz'

    zsr = str(zsr_number).strip().upper()

    try:
        # MedReg unterstuetzt Suche ueber Query-Parameter
        response = requests.get(
            MEDREG_API_URL,
            params={'zsr': zsr},
            timeout=10,
            headers={'Accept': 'application/json'}
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list) and len(data) > 0:
                return _parse_medreg_response(data[0]), None
            elif isinstance(data, dict):
                return _parse_medreg_response(data), None
            return None, f'Kein Eintrag gefunden fuer ZSR {zsr}'
        else:
            return None, f'API-Fehler: Status {response.status_code}'
    except requests.RequestException as e:
        logger.error(f'MedReg API nicht erreichbar: {e}')
        return None, f'Verbindungsfehler: {str(e)}'


def search_practitioners(name=None, specialty=None, canton=None, limit=20):
    """Freie Suche nach Leistungserbringern.

    Args:
        name: Vor- oder Nachname
        specialty: Fachgebiet
        canton: Kanton (z.B. 'ZH', 'BE')
        limit: Maximale Anzahl Ergebnisse

    Returns:
        list mit Arztdaten-Dicts
    """
    params = {}
    if name:
        params['name'] = name
    if specialty:
        params['specialty'] = specialty
    if canton:
        params['canton'] = canton
    params['limit'] = min(limit, 50)

    if not params:
        return [], 'Mindestens ein Suchkriterium erforderlich'

    try:
        response = requests.get(
            MEDREG_API_URL,
            params=params,
            timeout=10,
            headers={'Accept': 'application/json'}
        )

        if response.status_code == 200:
            data = response.json()
            if isinstance(data, list):
                return [_parse_medreg_response(item) for item in data[:limit]], None
            return [], 'Keine Ergebnisse gefunden'
        else:
            return [], f'API-Fehler: Status {response.status_code}'
    except requests.RequestException as e:
        logger.error(f'MedReg API nicht erreichbar: {e}')
        return [], f'Verbindungsfehler: {str(e)}'


def _parse_medreg_response(data):
    """Parst die MedReg-API-Antwort in ein einheitliches Format."""
    if not data:
        return None

    return {
        'salutation': data.get('title', '') or data.get('salutation', ''),
        'first_name': data.get('firstName', '') or data.get('first_name', ''),
        'last_name': data.get('lastName', '') or data.get('last_name', ''),
        'specialty': data.get('specialty', '') or data.get('profession', ''),
        'gln_number': str(data.get('gln', '') or data.get('glnNumber', '')),
        'zsr_number': str(data.get('zsrNumber', '') or data.get('zsr', '')),
        'address': data.get('street', '') or data.get('address', ''),
        'zip_code': str(data.get('zipCode', '') or data.get('zip', '')),
        'city': data.get('city', '') or data.get('place', ''),
        'canton': data.get('canton', ''),
        'phone': data.get('phone', '') or data.get('telephone', ''),
        'email': data.get('email', ''),
        'language': data.get('language', ''),
    }
