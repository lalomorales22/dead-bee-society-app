import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, flash, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from werkzeug.security import generate_password_hash, check_password_hash
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

@app.route('/')
def index():
    posts = Post.query.order_by(Post.timestamp.desc()).all()
    return render_template('index.html', posts=posts)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = LoginForm()
    if form.validate_on_submit():
        user = User.query.filter_by(username=form.username.data).first()
        if user and user.check_password(form.password.data):
            login_user(user)
            flash('Logged in successfully.', 'success')
            next_page = request.args.get('next')
            return redirect(next_page or url_for('index'))
        else:
            flash('Invalid username or password', 'error')
    return render_template('login.html', form=form)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('index'))
    form = RegistrationForm()
    if form.validate_on_submit():
        user = User(username=form.username.data, email=form.email.data)
        user.set_password(form.password.data)
        db.session.add(user)
        db.session.commit()
        flash('Congratulations, you are now a registered user!', 'success')
        return redirect(url_for('login'))
    return render_template('register.html', title='Register', form=form)

@app.route('/profile/<username>', methods=['GET', 'POST'])
def profile(username):
    user = User.query.filter_by(username=username).first_or_404()
    form = ProfileForm()
    if form.validate_on_submit() and current_user.is_authenticated and user == current_user:
        user.avatar = form.avatar.data
        user.bio = form.bio.data
        db.session.commit()
        flash('Your profile has been updated!', 'success')
        return redirect(url_for('profile', username=username))
    elif request.method == 'GET' and current_user.is_authenticated and user == current_user:
        form.avatar.data = user.avatar
        form.bio.data = user.bio
    posts = Post.query.filter_by(author=user).order_by(Post.timestamp.desc()).all()
    return render_template('profile.html', user=user, form=form, posts=posts)

@app.route('/search')
def search():
    query = request.args.get('query', '')
    users = User.query.filter(User.username.ilike(f'%{query}%')).all()
    posts = Post.query.filter(Post.content.ilike(f'%{query}%')).all()
    categories = Category.query.filter(Category.name.ilike(f'%{query}%')).all()
    return render_template('search_results.html', query=query, users=users, posts=posts, categories=categories)

@app.route('/category/<int:category_id>')
def category_posts(category_id):
    category = Category.query.get_or_404(category_id)
    posts = Post.query.filter(Post.categories.contains(category)).order_by(Post.timestamp.desc()).all()
    return render_template('category_posts.html', category=category, posts=posts)

if __name__ == '__main__':
    with app.app_context():
        db.create_all()
    app.run(host="0.0.0.0", port=5000, debug=True)
