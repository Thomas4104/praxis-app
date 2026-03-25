from flask import Blueprint

archive_bp = Blueprint('archive', __name__, template_folder='templates')

from blueprints.archive import routes
