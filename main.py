import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash
from models import db, User, Post, Comment, Category, Notification
from forms import RegistrationForm, LoginForm, PostForm, CommentForm, ProfileForm, CategoryForm
from config import Config
from utils import generate_dead_bee_image
import logging
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy import or_

load_dotenv()

app = Flask(__name__)
app.config.from_object(Config)

db.init_app(app)
migrate = Migrate(app, db)

login_manager = LoginManager(app)
login_manager.login_view = 'login'

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

@login_manager.user_loader
def load_user(user_id):
    return User.query.get(int(user_id))

def create_tables():
    with app.app_context():
        db.create_all()

def update_schema():
    with app.app_context():
        db.drop_all()
        db.create_all()
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
    for post in posts:
        logger.debug(f"Post ID: {post.id}, Image URL length: {len(post.image_url) if post.image_url else 'None'}")
        logger.debug(f"Post ID: {post.id}, Image URL preview: {post.image_url[:100] if post.image_url else 'None'}...")
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
            flash('An error occurred during registration. Please try again.', 'error')
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Unexpected error during user registration: {str(e)}")
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
    form.categories.choices = [(c.id, c.name) for c in Category.query.order_by('name')]
    if form.validate_on_submit():
        logger.debug(f"Generating image for message: {form.content.data}")
        image_data, error = generate_dead_bee_image(form.content.data)
        if error:
            logger.error(f"Error generating image: {error}")
            flash(f"Error generating image: {error}", 'error')
            return render_template('post.html', form=form, title='New Post')

        logger.debug(f"Image data received. Length: {len(image_data) if image_data else 'None'}")
        post = Post(content=form.content.data, image_url=image_data, author=current_user)
        selected_categories = Category.query.filter(Category.id.in_(form.categories.data)).all()
        post.categories = selected_categories
        db.session.add(post)
        db.session.commit()
        logger.info(f"New post created by user {current_user.username}")
        logger.debug(f"Post content: {post.content}")
        logger.debug(f"Post image_url length: {len(post.image_url) if post.image_url else 'None'}")
        logger.debug(f"Post image_url preview: {post.image_url[:100] if post.image_url else 'None'}...")
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

@app.route('/profile/<username>', methods=['GET', 'POST'])
@login_required
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    form = ProfileForm()
    if form.validate_on_submit() and user == current_user:
        user.avatar = form.avatar.data
        user.bio = form.bio.data
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile', username=username))
    elif request.method == 'GET':
        form.avatar.data = user.avatar
        form.bio.data = user.bio
    posts = Post.query.filter_by(author=user).order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, form=form, posts=posts)

@app.route('/follow/<username>')
@login_required
def follow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('index'))
    if user == current_user:
        flash('You cannot follow yourself!', 'error')
        return redirect(url_for('profile', username=username))
    current_user.follow(user)
    db.session.commit()
    flash(f'You are now following {username}!', 'success')
    notification = Notification(user_id=user.id, message=f'{current_user.username} started following you.')
    db.session.add(notification)
    db.session.commit()
    return redirect(url_for('profile', username=username))

@app.route('/unfollow/<username>')
@login_required
def unfollow(username):
    user = User.query.filter_by(username=username).first()
    if user is None:
        flash('User not found.', 'error')
        return redirect(url_for('index'))
    if user == current_user:
        flash('You cannot unfollow yourself!', 'error')
        return redirect(url_for('profile', username=username))
    current_user.unfollow(user)
    db.session.commit()
    flash(f'You have unfollowed {username}.', 'success')
    return redirect(url_for('profile', username=username))

@app.route('/notifications')
@login_required
def notifications():
    notifications = Notification.query.filter_by(user_id=current_user.id, is_read=False).order_by(Notification.timestamp.desc()).all()
    return render_template('notifications.html', notifications=notifications)

@app.route('/mark_notification_read/<int:notification_id>')
@login_required
def mark_notification_read(notification_id):
    notification = Notification.query.get_or_404(notification_id)
    if notification.user_id != current_user.id:
        flash('You do not have permission to mark this notification as read.', 'error')
        return redirect(url_for('notifications'))
    notification.is_read = True
    db.session.commit()
    return redirect(url_for('notifications'))

@app.route('/search')
def search():
    query = request.args.get('query', '')
    if query:
        posts = Post.query.filter(Post.content.ilike(f'%{query}%')).all()
        users = User.query.filter(or_(User.username.ilike(f'%{query}%'), User.email.ilike(f'%{query}%'))).all()
        categories = Category.query.filter(Category.name.ilike(f'%{query}%')).all()
    else:
        posts = []
        users = []
        categories = []
    return render_template('search_results.html', query=query, posts=posts, users=users, categories=categories)

@app.route('/category/new', methods=['GET', 'POST'])
@login_required
def new_category():
    form = CategoryForm()
    if form.validate_on_submit():
        category = Category(name=form.name.data)
        db.session.add(category)
        db.session.commit()
        flash('New category has been created!', 'success')
        return redirect(url_for('index'))
    return render_template('category.html', form=form, title='New Category')

@app.route('/category/<int:category_id>')
def category_posts(category_id):
    category = Category.query.get_or_404(category_id)
    posts = Post.query.filter(Post.categories.contains(category)).order_by(Post.timestamp.desc()).all()
    return render_template('category_posts.html', category=category, posts=posts)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)