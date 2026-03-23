from flask import Blueprint

addresses_bp = Blueprint('addresses', __name__, template_folder='templates')

from blueprints.addresses import routes
