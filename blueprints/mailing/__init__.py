from flask import Blueprint

mailing_bp = Blueprint('mailing', __name__, template_folder='templates')

from blueprints.mailing import routes
