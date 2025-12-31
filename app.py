"""
PrintKe - Kenya's Premier Online Card Printing Service
Main Application Entry Point
"""
import os
import logging
from flask import Flask, render_template, jsonify, request
from flask_cors import CORS
from flask_login import LoginManager
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from werkzeug.middleware.proxy_fix import ProxyFix

from config.settings import config
from src.models import db, User

# Initialize migrate outside of create_app for CLI access
migrate = Migrate()


def create_app(config_name=None):
    """Application factory"""
    if config_name is None:
        config_name = os.getenv('FLASK_ENV', 'development')

    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')

    # Load configuration
    app.config.from_object(config[config_name])

    # Handle proxy headers for HTTPS behind reverse proxy
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

    # Setup logging
    logging.basicConfig(
        level=logging.DEBUG if app.debug else logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    logger = logging.getLogger(__name__)

    # Initialize extensions
    db.init_app(app)
    migrate.init_app(app, db)

    # CORS with security
    cors_origins = os.getenv('CORS_ORIGINS', '*').split(',')
    CORS(app, origins=cors_origins, supports_credentials=True)

    # Rate limiting
    limiter = Limiter(
        key_func=get_remote_address,
        app=app,
        storage_uri=os.getenv('RATELIMIT_STORAGE_URL', 'memory://'),
        default_limits=['200 per day', '50 per hour']
    )

    # Apply stricter limits to sensitive endpoints
    @app.before_request
    def apply_rate_limits():
        """Apply endpoint-specific rate limits"""
        pass  # Limiter decorators applied directly to routes

    # Security headers
    @app.after_request
    def add_security_headers(response):
        """Add security headers to all responses"""
        # Prevent clickjacking
        response.headers['X-Frame-Options'] = 'SAMEORIGIN'
        # Prevent MIME type sniffing
        response.headers['X-Content-Type-Options'] = 'nosniff'
        # XSS Protection
        response.headers['X-XSS-Protection'] = '1; mode=block'
        # Referrer Policy
        response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
        # Content Security Policy (basic - customize for production)
        if not app.debug:
            response.headers['Content-Security-Policy'] = (
                "default-src 'self'; "
                "script-src 'self' 'unsafe-inline' https://unpkg.com; "
                "style-src 'self' 'unsafe-inline' https://fonts.googleapis.com https://unpkg.com; "
                "font-src 'self' https://fonts.gstatic.com; "
                "img-src 'self' data: https://*.tile.openstreetmap.org; "
                "connect-src 'self'"
            )
        # HTTPS enforcement in production
        if not app.debug:
            response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
        return response

    # Store limiter for use in blueprints
    app.limiter = limiter

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

    # Apply rate limits to sensitive endpoints
    limiter.limit("10 per minute")(orders_bp)  # Order creation
    limiter.limit("5 per minute")(payments_bp)  # Payment initiation
    limiter.limit("5 per minute")(admin_bp)  # Admin login attempts

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
    @app.errorhandler(400)
    def bad_request(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Bad request', 'message': str(e.description)}), 400
        return render_template('errors/400.html'), 400

    @app.errorhandler(401)
    def unauthorized(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Unauthorized'}), 401
        return render_template('errors/401.html'), 401

    @app.errorhandler(403)
    def forbidden(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Forbidden'}), 403
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Not found'}), 404
        return render_template('errors/404.html'), 404

    @app.errorhandler(429)
    def ratelimit_handler(e):
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Rate limit exceeded. Please try again later.'}), 429
        return render_template('errors/429.html'), 429

    @app.errorhandler(500)
    def server_error(e):
        logger.error(f"Server error: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'Internal server error'}), 500
        return render_template('errors/500.html'), 500

    @app.errorhandler(Exception)
    def handle_exception(e):
        """Handle all unhandled exceptions"""
        logger.error(f"Unhandled exception: {e}", exc_info=True)
        if request.path.startswith('/api/'):
            return jsonify({'error': 'An unexpected error occurred'}), 500
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
