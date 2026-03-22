# Abrechnungs-Blueprint: Rechnungen, Zahlungen, Mahnwesen
from flask import Blueprint

billing_bp = Blueprint('billing', __name__, template_folder='templates')

from blueprints.billing import routes  # noqa
