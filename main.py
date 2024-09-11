from flask import Flask, render_template, redirect, url_for, flash, request
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from models import db, User, Post, Comment
from forms import RegistrationForm, LoginForm, PostForm, CommentForm
from config import Config
from utils import generate_dead_bee_image
import logging
from sqlalchemy.exc import SQLAlchemyError

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
login_manager = LoginManager(app)
login_manager.login_view = 'login'

logging.basicConfig(level=logging.INFO)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_tables():
    with app.app_context():
        db.create_all()

def update_schema():
    with app.app_context():
        db.drop_all()  # This will drop all existing tables
        db.create_all()  # This will recreate all tables with the updated schema
        db.session.commit()

def test_db_connection():
    with app.app_context():
        try:
            db.session.execute('SELECT 1')
            app.logger.info("Database connection successful")
        except SQLAlchemyError as e:
            app.logger.error(f"Database connection error: {str(e)}")
            app.logger.error(f"Error code: {e.code if hasattr(e, 'code') else 'N/A'}")
            app.logger.error(f"Error details: {e.orig if hasattr(e, 'orig') else 'N/A'}")

@app.route('/')
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    form = CommentForm()
    return render_template('index.html', posts=posts, form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    form = RegistrationForm()
    if form.validate_on_submit():
        try:
            app.logger.info(f"Attempting to register user: {form.username.data}")
            user = User(username=form.username.data, email=form.email.data)
            user.set_password(form.password.data)
            db.session.add(user)
            db.session.commit()
            app.logger.info(f"User {form.username.data} registered successfully")
            flash('Registration successful. Please log in.', 'success')
            return redirect(url_for('login'))
        except SQLAlchemyError as e:
            db.session.rollback()
            app.logger.error(f"SQLAlchemy error during user registration: {str(e)}")
            app.logger.error(f"Error code: {e.code if hasattr(e, 'code') else 'N/A'}")
            app.logger.error(f"Error details: {e.orig if hasattr(e, 'orig') else 'N/A'}")
            flash('An error occurred during registration. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Unexpected error during user registration: {str(e)}")
            app.logger.error(f"Exception type: {type(e).__name__}")
            app.logger.error(f"Exception details: {e.args}")
            flash('An unexpected error occurred during registration. Please try again.', 'error')
    return render_template('register.html', form=form)

@app.route('/login', methods=['GET', 'POST'])
def login():
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            return redirect(url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html', form=form)

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/post/new', methods=['GET', 'POST'])
@login_required
def new_post():
    form = PostForm()
    if form.validate_on_submit():
        image_url = generate_dead_bee_image()
        post = Post(content=form.content.data, image_url=image_url, author=current_user)
        db.session.add(post)
        db.session.commit()
        flash('Your post has been created!', 'success')
        return redirect(url_for('index'))
    return render_template('post.html', form=form, title='New Post')

@app.route('/post/<int:post_id>/comment', methods=['POST'])
@login_required
def comment_post(post_id):
    post = Post.query.get_or_404(post_id)
    form = CommentForm()
    if form.validate_on_submit():
        comment = Comment(content=form.content.data, post=post, author=current_user)
        db.session.add(comment)
        db.session.commit()
        flash('Your comment has been added!', 'success')
    return redirect(url_for('index'))

if __name__ == '__main__':
    with app.app_context():
        update_schema()  # This will force a schema update
        test_db_connection()  # Test the database connection before running the app
    app.run(host="0.0.0.0", port=5000)
