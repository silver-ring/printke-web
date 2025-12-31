"""
PrintKe - Kenya's Premier Online Card Printing Service
Main Application Entry Point
"""
import os
import logging
from flask import Flask, render_template, jsonify
from flask_cors import CORS
from flask_login import LoginManager

from config.settings import config
from src.models import db, User


def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')

    # Load configuration
    app.config.from_object(config[config_name])

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Initialize extensions
    db.init_app(app)
    CORS(app)

    # Setup Flask-Login
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'main.login'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Ensure folders exist
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'originals'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'processed'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'pdfs'), exist_ok=True)

    # Register blueprints
    from src.api.orders import orders_bp
    from src.api.payments import payments_bp
    from src.api.admin import admin_bp

    app.register_blueprint(orders_bp)
    app.register_blueprint(payments_bp)
    app.register_blueprint(admin_bp)

    # Main routes
    @app.route('/')
    def index():
        return render_template('customer/index.html')

    @app.route('/order')
    def order_page():
        return render_template('customer/order.html')

    @app.route('/order/<order_number>')
    def order_status(order_number):
        # Redirect to tracking page
        return render_template('customer/tracking.html', order_number=order_number)

    @app.route('/track/<order_number>')
    def tracking_page(order_number):
        return render_template('customer/tracking.html', order_number=order_number)

    @app.route('/payment/<order_number>')
    def payment_page(order_number):
        return render_template('customer/payment.html', order_number=order_number)

    @app.route('/pricing')
    def pricing():
        return render_template('customer/pricing.html')

    @app.route('/templates')
    def card_templates():
        return render_template('customer/templates.html')

    @app.route('/contact')
    def contact():
        return render_template('customer/contact.html')

    @app.route('/about')
    def about():
        return render_template('customer/about.html')

    @app.route('/admin')
    def admin_dashboard():
        return render_template('admin/dashboard.html')

    @app.route('/admin/orders')
    def admin_orders():
        return render_template('admin/orders.html')

    @app.route('/admin/orders/<order_number>')
    def admin_order_detail(order_number):
        return render_template('admin/order_detail.html', order_number=order_number)

    # Health check
    @app.route('/health')
    def health():
        return jsonify({'status': 'healthy', 'mock_mode': app.config.get('MOCK_PRINTING', True)})

    # Error handlers
    @app.errorhandler(404)
    def not_found(e):
        if 'api' in str(e):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}")
        if 'api' in str(e):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500

    # Create database tables
    with app.app_context():
        db.create_all()

        # Create default admin user if not exists
        if not User.query.filter_by(email='admin@printke.co.ke').first():
            admin = User(
                email='admin@printke.co.ke',
                phone='+254700000000',
                first_name='Admin',
                last_name='PrintKe',
                is_admin=True
            )
            admin.set_password('admin123')  # Change in production!
            db.session.add(admin)
            db.session.commit()
            logger.info("Created default admin user")

        # Create default products if not exist
        from src.models import Product
        if not Product.query.first():
            products = [
                Product(
                    name='Standard PVC ID Card',
                    slug='standard-pvc',
                    description='High-quality CR80 PVC card with full-color printing',
                    card_type='pvc',
                    is_double_sided=True,
                    base_price=300
                ),
                Product(
                    name='Single-Sided Card',
                    slug='single-sided',
                    description='Single-sided CR80 PVC card',
                    card_type='pvc',
                    is_double_sided=False,
                    base_price=200
                ),
                Product(
                    name='Premium Matte Card',
                    slug='premium-matte',
                    description='Premium matte finish CR80 card',
                    card_type='pvc',
                    is_double_sided=True,
                    base_price=350
                ),
            ]
            for product in products:
                db.session.add(product)
            db.session.commit()
            logger.info("Created default products")

    return app


# Create application instance
app = create_app()


if __name__ == '__main__':
    print("=" * 60)
    print("  PrintKe - Kenya's Premier Card Printing Service")
    print(f"  MOCK MODE: {app.config.get('MOCK_PRINTING', True)}")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True)
