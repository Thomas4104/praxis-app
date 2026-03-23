from datetime import datetime
from flask import render_template, request, redirect, url_for, flash, jsonify
from flask_login import login_required, current_user
from blueprints.products import products_bp
from models import db, Product, ProductPriceHistory, TreatmentSeries
from utils.auth import check_org


@products_bp.route('/')
@login_required
def index():
    """Produktuebersicht mit Suche, Filter und Sortierung"""
    search = request.args.get('search', '').strip()
    category = request.args.get('category', '')
    status = request.args.get('status', 'active')
    sort = request.args.get('sort', 'name')
    order = request.args.get('order', 'asc')

    query = Product.query.filter_by(organization_id=current_user.organization_id)

    # Status-Filter
    if status == 'active':
        query = query.filter_by(is_active=True)
    elif status == 'inactive':
        query = query.filter_by(is_active=False)
    # 'all' zeigt alles

    # Suchfilter
    if search:
        query = query.filter(
            db.or_(
                Product.name.ilike(f'%{search}%'),
                Product.article_number.ilike(f'%{search}%')
            )
        )

    # Kategorie-Filter
    if category:
        query = query.filter_by(category=category)

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

    products = query.all()

    return render_template('products/index.html',
                           products=products,
                           search=search,
                           category=category,
                           status=status,
                           sort=sort,
                           order=order)


@products_bp.route('/new', methods=['GET', 'POST'])
@login_required
def create():
    """Neues Produkt erstellen"""
    if request.method == 'POST':
        return _save_product(None)

    return render_template('products/form.html', product=None)


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

    # Verknuepfte Behandlungsserien
    # Serien die dieses Produkt im Titel oder in Notizen erwaehnen
    linked_series = []

    return render_template('products/detail.html',
                           product=product,
                           price_history=price_history,
                           linked_series=linked_series)


@products_bp.route('/<int:product_id>/edit', methods=['GET', 'POST'])
@login_required
def edit(product_id):
    """Produkt bearbeiten"""
    product = Product.query.get_or_404(product_id)
    check_org(product)

    if request.method == 'POST':
        return _save_product(product)

    return render_template('products/form.html', product=product)


@products_bp.route('/<int:product_id>/toggle', methods=['POST'])
@login_required
def toggle_active(product_id):
    """Produkt aktivieren/deaktivieren"""
    product = Product.query.get_or_404(product_id)
    check_org(product)
    product.is_active = not product.is_active
    db.session.commit()

    status_text = 'aktiviert' if product.is_active else 'deaktiviert'
    flash(f'Produkt "{product.name}" wurde {status_text}.', 'success')
    return redirect(url_for('products.index'))


def _save_product(product):
    """Speichert ein Produkt (neu oder bestehend)"""
    name = request.form.get('name', '').strip()
    net_price_str = request.form.get('net_price', '0').strip().replace(',', '.')

    # Validierung
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
        if product:
            return render_template('products/form.html', product=product)
        else:
            return render_template('products/form.html', product=None)

    is_new = product is None
    if is_new:
        product = Product(organization_id=current_user.organization_id)

    # Preis-Aenderung tracken
    old_price = product.net_price if not is_new else None
    if old_price is not None and old_price != net_price:
        history = ProductPriceHistory(
            product_id=product.id,
            old_price=old_price,
            new_price=net_price,
            changed_by_id=current_user.id
        )
        db.session.add(history)

    product.name = name
    product.description = request.form.get('description', '').strip()
    product.category = request.form.get('category', '')
    product.net_price = net_price
    product.vat_rate = float(request.form.get('vat_rate', '0').replace(',', '.'))
    product.unit_type = request.form.get('unit_type', '')
    product.tariff_code = request.form.get('tariff_code', '').strip()
    product.supplier = request.form.get('supplier', '').strip()
    product.manufacturer = request.form.get('manufacturer', '').strip()
    product.article_number = request.form.get('article_number', '').strip()

    try:
        product.stock_quantity = int(request.form.get('stock_quantity', '0'))
    except ValueError:
        product.stock_quantity = 0

    try:
        product.min_stock = int(request.form.get('min_stock', '0'))
    except ValueError:
        product.min_stock = 0

    product.is_active = request.form.get('is_active') == 'on'

    if is_new:
        db.session.add(product)

    db.session.commit()

    flash(f'Produkt "{product.name}" wurde erfolgreich gespeichert.', 'success')
    return redirect(url_for('products.detail', product_id=product.id))
