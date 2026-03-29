import json
import os
from datetime import datetime, timezone
from flask import render_template, request, redirect, url_for, flash, jsonify, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
from blueprints.products import products_bp
from models import db, Product, ProductPriceHistory, ProductTag, Contact, BankAccount
from utils.auth import check_org
from services.user_rights_service import require_right


# Cenplex Produkt-Kategorien (ProductCategory Enum)
PRODUCT_CATEGORIES = [
    ('', '-- Kategorie waehlen --'),
    ('Bandage', 'Bandagen'),
    ('Tape', 'Tapen'),
    ('Beckenboden', 'Beckenboden'),
    ('Electro', 'Elektrotherapie'),
    ('Breath', 'Atemtherapie'),
    ('DryNeedling', 'Dry Needling'),
]

# Cenplex Einheiten (UnitType Enum)
UNIT_TYPES = [
    ('', '-- Einheit waehlen --'),
    ('Stueck', 'Stueck'),
    ('cm', 'Zentimeter'),
    ('m', 'Meter'),
    ('Tage', 'Tage'),
    ('Monate', 'Monate'),
]

# Cenplex MwSt-Saetze (Schweiz ab 2024)
VAT_RATES = [
    ('0', '0% (Befreit)'),
    ('2.6', '2.6% (Reduziert)'),
    ('3.8', '3.8% (Sondersatz)'),
    ('8.1', '8.1% (Normal)'),
]

# Cenplex Ergo-Taxpunkte
ERGO_TAXPOINTS = [
    3201, 3211, 3212, 3213, 3231, 3241, 3242, 3243, 3244, 3261, 3262, 3263, 7644, 7645, 7646
]


@products_bp.route('/')
@login_required
@require_right('product', 'can_read')
def index():
    """Produktuebersicht mit Suche, Filter und Sortierung"""
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')
    status = request.args.get('status', 'active')
    tag_id = request.args.get('tag', '', type=str)
    sort = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')

    org_id = current_user.organization_id
    query = Product.query.filter_by(organization_id=org_id)

    # Status-Filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)

    # Suchfilter (Name, Artikelnummer, Beschreibung, MIGE-Nummer - wie Cenplex Matches())
    if search:
        search_terms = search.split()
        for term in search_terms:
            pattern = f'%{term}%'
            query = query.filter(
                db.or_(
                    Product.name.ilike(pattern),
                    Product.article_number.ilike(pattern),
                    Product.description.ilike(pattern),
                    Product.mige_number.ilike(pattern),
                    Product.category.ilike(pattern),
                )
            )

    # Kategorie-Filter
    if category:
        query = query.filter_by(category=category)

    # Tag-Filter
    if tag_id:
        query = query.filter(Product.tags.like(f'%"{tag_id}"%'))

    # Sortierung
    sort_column = {
        'name': Product.name,
        'price': Product.net_price,
        'stock': Product.stock_quantity,
        'category': Product.category
    }.get(sort, Product.name)

    if order == 'desc':
        query = query.order_by(sort_column.desc())
    else:
        query = query.order_by(sort_column.asc())

    # Pagination
    page = request.args.get('page', 1, type=int)
    per_page = 25
    total = query.count()
    products = query.offset((page - 1) * per_page).limit(per_page).all()
    total_pages = (total + per_page - 1) // per_page

    # Tags laden fuer Filter-Dropdown
    tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()

    # Tag-Namen fuer Produkte aufloesen
    tag_map = {str(t.id): t.name for t in tags}

    return render_template('products/index.html',
                           products=products,
                           search=search,
                           category=category,
                           status=status,
                           tag_id=tag_id,
                           sort=sort,
                           order=order,
                           page=page,
                           total_pages=total_pages,
                           total=total,
                           tags=tags,
                           tag_map=tag_map,
                           categories=PRODUCT_CATEGORIES)


@products_bp.route('/new', methods=['GET', 'POST'])
@login_required
@require_right('product', 'can_edit')
def create():
    """Neues Produkt erstellen"""
    if request.method == 'POST':
        return _save_product(None)

    org_id = current_user.organization_id
    contacts = Contact.query.filter_by(organization_id=org_id, is_active=True).order_by(Contact.company_name, Contact.last_name).all()
    bank_accounts = BankAccount.query.filter_by(organization_id=org_id, is_active=True).order_by(BankAccount.bank_name).all()
    tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()

    return render_template('products/form.html',
                           product=None,
                           contacts=contacts,
                           bank_accounts=bank_accounts,
                           tags=tags,
                           categories=PRODUCT_CATEGORIES,
                           unit_types=UNIT_TYPES,
                           vat_rates=VAT_RATES,
                           ergo_taxpoints=ERGO_TAXPOINTS,
                           selected_tags=[])


@products_bp.route('/<int:product_id>')
@login_required
def detail(product_id):
    """Produkt-Detailansicht"""
    product = Product.query.get_or_404(product_id)
    check_org(product)

    # Preis-Historie laden
    price_history = ProductPriceHistory.query.filter_by(
        product_id=product_id
    ).order_by(ProductPriceHistory.changed_at.desc()).all()

    # Tags aufloesen
    org_id = current_user.organization_id
    tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()
    tag_map = {str(t.id): t.name for t in tags}
    selected_tags = _get_product_tags(product)

    return render_template('products/detail.html',
                           product=product,
                           price_history=price_history,
                           tag_map=tag_map,
                           selected_tags=selected_tags,
                           categories=PRODUCT_CATEGORIES,
                           unit_types=UNIT_TYPES,
                           vat_rates=VAT_RATES,
                           ergo_taxpoints=ERGO_TAXPOINTS)


@products_bp.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
@require_right('product', 'can_edit')
def edit(product_id):
    """Produkt bearbeiten"""
    product = Product.query.get_or_404(product_id)
    check_org(product)

    if request.method == 'POST':
        return _save_product(product)

    org_id = current_user.organization_id
    contacts = Contact.query.filter_by(organization_id=org_id, is_active=True).order_by(Contact.company_name, Contact.last_name).all()
    bank_accounts = BankAccount.query.filter_by(organization_id=org_id, is_active=True).order_by(BankAccount.bank_name).all()
    tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()
    selected_tags = _get_product_tags(product)

    return render_template('products/form.html',
                           product=product,
                           contacts=contacts,
                           bank_accounts=bank_accounts,
                           tags=tags,
                           categories=PRODUCT_CATEGORIES,
                           unit_types=UNIT_TYPES,
                           vat_rates=VAT_RATES,
                           ergo_taxpoints=ERGO_TAXPOINTS,
                           selected_tags=selected_tags)


@products_bp.route('/<int:product_id>/toggle', methods=['POST'])
@login_required
@require_right('product', 'can_edit')
def toggle_active(product_id):
    """Produkt aktivieren/deaktivieren (Cenplex: ActivateProduct/DeactivateProduct)"""
    product = Product.query.get_or_404(product_id)
    check_org(product)
    product.is_active = not product.is_active
    db.session.commit()

    status_text = 'aktiviert' if product.is_active else 'deaktiviert'
    flash(f'Produkt "{product.name}" wurde {status_text}.', 'success')
    return redirect(url_for('products.index'))


# ============================================================
# Tag-Verwaltung (Cenplex: ProductCategoryViewModel)
# ============================================================

@products_bp.route('/tags')
@login_required
def tags_index():
    """Tag-Verwaltung - Liste aller Tags"""
    org_id = current_user.organization_id
    tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()

    # Produkt-Anzahl pro Tag berechnen
    products = Product.query.filter_by(organization_id=org_id).all()
    tag_counts = {}
    for tag in tags:
        count = 0
        for p in products:
            if p.tags:
                try:
                    tag_ids = json.loads(p.tags)
                    if str(tag.id) in tag_ids:
                        count += 1
                except (json.JSONDecodeError, TypeError):
                    pass
            tag_counts[tag.id] = count

    return render_template('products/tags.html',
                           tags=tags,
                           tag_counts=tag_counts)


@products_bp.route('/tags/new', methods=['POST'])
@login_required
def tag_create():
    """Neuen Tag erstellen"""
    name = request.form.get('name', '').strip()
    if not name:
        flash('Tag-Name ist ein Pflichtfeld.', 'error')
        return redirect(url_for('products.tags_index'))

    org_id = current_user.organization_id

    # Duplikat pruefen
    existing = ProductTag.query.filter_by(organization_id=org_id, name=name).first()
    if existing:
        flash(f'Tag "{name}" existiert bereits.', 'error')
        return redirect(url_for('products.tags_index'))

    tag = ProductTag(organization_id=org_id, name=name)
    db.session.add(tag)
    db.session.commit()

    flash(f'Tag "{name}" wurde erstellt.', 'success')
    return redirect(url_for('products.tags_index'))


@products_bp.route('/tags/<int:tag_id>/delete', methods=['POST'])
@login_required
def tag_delete(tag_id):
    """Tag loeschen und aus allen Produkten entfernen (Cenplex: DeleteTags)"""
    tag = ProductTag.query.get_or_404(tag_id)
    if tag.organization_id != current_user.organization_id:
        flash('Keine Berechtigung.', 'error')
        return redirect(url_for('products.tags_index'))

    # Tag aus allen Produkten entfernen
    org_id = current_user.organization_id
    products = Product.query.filter_by(organization_id=org_id).all()
    tag_id_str = str(tag_id)
    for p in products:
        if p.tags:
            try:
                tag_ids = json.loads(p.tags)
                if tag_id_str in tag_ids:
                    tag_ids.remove(tag_id_str)
                    p.tags = json.dumps(tag_ids) if tag_ids else None
            except (json.JSONDecodeError, TypeError):
                pass

    tag_name = tag.name
    db.session.delete(tag)
    db.session.commit()

    flash(f'Tag "{tag_name}" wurde geloescht.', 'success')
    return redirect(url_for('products.tags_index'))


@products_bp.route('/tags/<int:tag_id>/products', methods=['POST'])
@login_required
def tag_update_products(tag_id):
    """Produkte fuer einen Tag aktualisieren (Cenplex: UpdateTags Batch)"""
    tag = ProductTag.query.get_or_404(tag_id)
    if tag.organization_id != current_user.organization_id:
        flash('Keine Berechtigung.', 'error')
        return redirect(url_for('products.tags_index'))

    org_id = current_user.organization_id
    selected_product_ids = request.form.getlist('product_ids')
    selected_set = set(selected_product_ids)
    tag_id_str = str(tag_id)

    products = Product.query.filter_by(organization_id=org_id).all()
    for p in products:
        tag_ids = []
        if p.tags:
            try:
                tag_ids = json.loads(p.tags)
            except (json.JSONDecodeError, TypeError):
                tag_ids = []

        pid_str = str(p.id)
        if pid_str in selected_set:
            # Tag hinzufuegen falls nicht vorhanden
            if tag_id_str not in tag_ids:
                tag_ids.append(tag_id_str)
                p.tags = json.dumps(tag_ids)
        else:
            # Tag entfernen falls vorhanden
            if tag_id_str in tag_ids:
                tag_ids.remove(tag_id_str)
                p.tags = json.dumps(tag_ids) if tag_ids else None

    db.session.commit()
    flash(f'Produkt-Zuordnungen fuer Tag "{tag.name}" wurden aktualisiert.', 'success')
    return redirect(url_for('products.tags_index'))


# ============================================================
# Hilfsfunktionen
# ============================================================

def _get_product_tags(product):
    """Tag-IDs eines Produkts als Liste zurueckgeben"""
    if not product or not product.tags:
        return []
    try:
        return json.loads(product.tags)
    except (json.JSONDecodeError, TypeError):
        return []


def _save_product(product):
    """Speichert ein Produkt (neu oder bestehend) mit allen Cenplex-Feldern"""
    name = request.form.get('name', '').strip()
    net_price_str = request.form.get('net_price', '0').strip().replace(',', '.')

    # Validierung (Cenplex: Name pflicht, Preis > 0)
    errors = []
    if not name:
        errors.append('Name ist ein Pflichtfeld.')

    try:
        net_price = float(net_price_str)
        if net_price < 0:
            errors.append('Der Nettopreis darf nicht negativ sein.')
    except ValueError:
        errors.append('Der Nettopreis muss eine gueltige Zahl sein.')
        net_price = 0.0

    if errors:
        for error in errors:
            flash(error, 'error')
        org_id = current_user.organization_id
        contacts = Contact.query.filter_by(organization_id=org_id, is_active=True).order_by(Contact.company_name, Contact.last_name).all()
        bank_accounts = BankAccount.query.filter_by(organization_id=org_id, is_active=True).order_by(BankAccount.bank_name).all()
        tags = ProductTag.query.filter_by(organization_id=org_id).order_by(ProductTag.name).all()
        selected_tags = request.form.getlist('tags')
        return render_template('products/form.html',
                               product=product,
                               contacts=contacts,
                               bank_accounts=bank_accounts,
                               tags=tags,
                               categories=PRODUCT_CATEGORIES,
                               unit_types=UNIT_TYPES,
                               vat_rates=VAT_RATES,
                               ergo_taxpoints=ERGO_TAXPOINTS,
                               selected_tags=selected_tags)

    is_new = product is None
    if is_new:
        product = Product(organization_id=current_user.organization_id)

    # Preis-Aenderung tracken
    old_price = product.net_price if not is_new else None
    if old_price is not None and float(old_price) != net_price:
        history = ProductPriceHistory(
            product_id=product.id,
            old_price=old_price,
            new_price=net_price,
            changed_by_id=current_user.id
        )
        db.session.add(history)

    # Basis-Felder
    product.name = name
    product.description = request.form.get('description', '').strip()
    product.category = request.form.get('category', '')
    product.net_price = net_price
    product.vat_rate = float(request.form.get('vat_rate', '0').replace(',', '.'))
    product.unit_type = request.form.get('unit_type', '')
    product.article_number = request.form.get('article_number', '').strip()

    # Cenplex-Felder
    product.order_number = request.form.get('order_number', '').strip() or None
    product.mige_number = request.form.get('mige_number', '').strip() or None
    product.product_tarif = request.form.get('product_tarif', '').strip() or None
    product.tariff_code = request.form.get('tariff_code', '').strip() or None

    # Lieferant als Kontakt-Referenz (Cenplex: ProviderDto)
    provider_id = request.form.get('provider_id', '')
    product.provider_id = int(provider_id) if provider_id else None
    # Auch Freitext-Lieferant behalten fuer Rueckwaertskompatibilitaet
    product.supplier = request.form.get('supplier', '').strip()
    product.manufacturer = request.form.get('manufacturer', '').strip()

    # Bankkonto (Cenplex: DefaultbankaccountDto)
    bank_id = request.form.get('default_bank_account_id', '')
    product.default_bank_account_id = int(bank_id) if bank_id else None

    # Ergo & EMR (Cenplex: IsergoDto, IsemrDto)
    product.is_ergo = request.form.get('is_ergo') == 'on'
    product.is_emr = request.form.get('is_emr') == 'on'

    # Ergo-Taxpunkt (Cenplex: ErgotaxpointDto)
    ergo_tp = request.form.get('ergo_taxpoint', '')
    if product.is_ergo and ergo_tp:
        product.ergo_taxpoint = int(ergo_tp)
    elif not product.is_ergo:
        product.ergo_taxpoint = None

    # Tags (Cenplex: TagsDto als JSON-Array von IDs)
    selected_tags = request.form.getlist('tags')
    product.tags = json.dumps(selected_tags) if selected_tags else None

    # Lagerbestand
    try:
        product.stock_quantity = int(request.form.get('stock_quantity', '0'))
    except ValueError:
        product.stock_quantity = 0
    try:
        product.min_stock = int(request.form.get('min_stock', '0'))
    except ValueError:
        product.min_stock = 0

    # Aktiv-Status
    product.is_active = request.form.get('is_active') == 'on'

    # Logo-Upload
    logo_file = request.files.get('logo')
    if logo_file and logo_file.filename:
        allowed = {'jpg', 'jpeg', 'png', 'gif', 'bmp'}
        ext = logo_file.filename.rsplit('.', 1)[-1].lower() if '.' in logo_file.filename else ''
        if ext in allowed:
            filename = secure_filename(f'product_{product.id or "new"}_{int(datetime.now(timezone.utc).timestamp())}.{ext}')
            upload_dir = os.path.join(current_app.static_folder, 'uploads', 'products')
            os.makedirs(upload_dir, exist_ok=True)
            filepath = os.path.join(upload_dir, filename)
            logo_file.save(filepath)
            product.logo_path = f'uploads/products/{filename}'
        else:
            flash('Ungueliges Bildformat. Erlaubt: JPG, PNG, GIF, BMP.', 'warning')

    if is_new:
        db.session.add(product)

    db.session.commit()

    flash(f'Produkt "{product.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('products.detail', product_id=product.id))
