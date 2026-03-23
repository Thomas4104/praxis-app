from flask import Blueprint

accounting_bp = Blueprint('accounting', __name__, template_folder='templates')

from blueprints.accounting import routes
