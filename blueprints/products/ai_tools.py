"""KI-Tools fuer den Produkte-Bereich"""
from models import db, Product


PRODUCT_TOOLS = [
    {
        'name': 'produkt_suchen',
        'description': 'Sucht Produkte nach Name oder Artikelnummer. Gibt eine Liste passender Produkte zurueck.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'suchbegriff': {
                    'type': 'string',
                    'description': 'Suchbegriff (Produktname oder Artikelnummer)'
                }
            },
            'required': ['suchbegriff']
        }
    },
    {
        'name': 'produkt_details',
        'description': 'Zeigt alle Details eines Produkts anhand der Produkt-ID.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'produkt_id': {
                    'type': 'integer',
                    'description': 'ID des Produkts'
                }
            },
            'required': ['produkt_id']
        }
    },
    {
        'name': 'lagerbestand_pruefen',
        'description': 'Prueft den aktuellen Lagerbestand und Mindestbestand eines Produkts.',
        'input_schema': {
            'type': 'object',
            'properties': {
                'produkt_id': {
                    'type': 'integer',
                    'description': 'ID des Produkts'
                }
            },
            'required': ['produkt_id']
        }
    },
    {
        'name': 'produkte_unter_mindestbestand',
        'description': 'Listet alle Produkte auf, deren aktueller Lagerbestand unter dem Mindestbestand liegt und die nachbestellt werden muessen.',
        'input_schema': {
            'type': 'object',
            'properties': {},
            'required': []
        }
    }
]


def product_tool_executor(tool_name, tool_input):
    """Fuehrt die Produkt-Tools aus"""

    if tool_name == 'produkt_suchen':
        suchbegriff = tool_input['suchbegriff'].strip()
        produkte = Product.query.filter(
            db.or_(
                Product.name.ilike(f'%{suchbegriff}%'),
                Product.article_number.ilike(f'%{suchbegriff}%')
            ),
            Product.is_active == True
        ).limit(20).all()

        if not produkte:
            return {'ergebnis': 'Keine Produkte gefunden.', 'anzahl': 0}

        ergebnisse = []
        for p in produkte:
            ergebnisse.append({
                'id': p.id,
                'name': p.name,
                'kategorie': p.category or 'Keine',
                'nettopreis': f'{p.net_price:.2f} CHF',
                'einheit': p.unit_type or '-',
                'lagerbestand': p.stock_quantity,
                'mindestbestand': p.min_stock,
                'artikelnummer': p.article_number or '-',
                'unter_mindestbestand': p.stock_quantity < p.min_stock if p.min_stock > 0 else False
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    elif tool_name == 'produkt_details':
        produkt = Product.query.get(tool_input['produkt_id'])
        if not produkt:
            return {'error': 'Produkt nicht gefunden.'}

        return {
            'ergebnis': {
                'id': produkt.id,
                'name': produkt.name,
                'beschreibung': produkt.description or '-',
                'kategorie': produkt.category or 'Keine',
                'nettopreis': f'{produkt.net_price:.2f} CHF',
                'mwst_satz': f'{produkt.vat_rate}%',
                'bruttopreis': f'{produkt.net_price * (1 + produkt.vat_rate / 100):.2f} CHF',
                'einheit': produkt.unit_type or '-',
                'tarifcode': produkt.tariff_code or '-',
                'lieferant': produkt.supplier or '-',
                'hersteller': produkt.manufacturer or '-',
                'artikelnummer': produkt.article_number or '-',
                'lagerbestand': produkt.stock_quantity,
                'mindestbestand': produkt.min_stock,
                'aktiv': produkt.is_active,
                'unter_mindestbestand': produkt.stock_quantity < produkt.min_stock if produkt.min_stock > 0 else False
            }
        }

    elif tool_name == 'lagerbestand_pruefen':
        produkt = Product.query.get(tool_input['produkt_id'])
        if not produkt:
            return {'error': 'Produkt nicht gefunden.'}

        unter_mindestbestand = produkt.stock_quantity < produkt.min_stock if produkt.min_stock > 0 else False

        return {
            'ergebnis': {
                'produkt': produkt.name,
                'lagerbestand': produkt.stock_quantity,
                'mindestbestand': produkt.min_stock,
                'einheit': produkt.unit_type or 'Stueck',
                'unter_mindestbestand': unter_mindestbestand,
                'warnung': f'ACHTUNG: Bestand ({produkt.stock_quantity}) liegt unter Mindestbestand ({produkt.min_stock})! Nachbestellung empfohlen.' if unter_mindestbestand else 'Bestand ist ausreichend.'
            }
        }

    elif tool_name == 'produkte_unter_mindestbestand':
        produkte = Product.query.filter(
            Product.is_active == True,
            Product.min_stock > 0,
            Product.stock_quantity < Product.min_stock
        ).order_by(Product.name).all()

        if not produkte:
            return {'ergebnis': 'Alle Produkte haben ausreichend Lagerbestand.', 'anzahl': 0}

        ergebnisse = []
        for p in produkte:
            ergebnisse.append({
                'id': p.id,
                'name': p.name,
                'lagerbestand': p.stock_quantity,
                'mindestbestand': p.min_stock,
                'fehlmenge': p.min_stock - p.stock_quantity,
                'einheit': p.unit_type or 'Stueck',
                'lieferant': p.supplier or 'Kein Lieferant hinterlegt'
            })

        return {'ergebnis': ergebnisse, 'anzahl': len(ergebnisse)}

    return {'error': f'Unbekanntes Tool: {tool_name}'}
