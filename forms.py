from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField
from wtforms.validators import DataRequired, Email, Length

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])

class PostForm(FlaskForm):
    content = TextAreaField('Content', validators=[DataRequired(), Length(max=500)])

class CommentForm(FlaskForm):
    content = TextAreaField('Comment', validators=[DataRequired(), Length(max=200)])
