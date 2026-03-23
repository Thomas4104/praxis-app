from flask import Blueprint

cost_approvals_bp = Blueprint('cost_approvals', __name__, template_folder='templates')

from blueprints.cost_approvals import routes
