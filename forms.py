from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, TextAreaField, SubmitField, SelectMultipleField
from wtforms.validators import DataRequired, Email, Length, URL, Optional

class RegistrationForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired(), Length(min=3, max=20)])
    email = StringField('Email', validators=[DataRequired(), Email()])
    password = PasswordField('Password', validators=[DataRequired()])
    avatar = StringField('Avatar URL', validators=[Optional(), URL()])
    submit = SubmitField('Register')

class LoginForm(FlaskForm):
    username = StringField('Username', validators=[DataRequired()])
    password = PasswordField('Password', validators=[DataRequired()])
    submit = SubmitField('Login')

class PostForm(FlaskForm):
    content = TextAreaField('Content', validators=[DataRequired(), Length(max=500)])
    categories = SelectMultipleField('Categories', coerce=int)
    submit = SubmitField('Post')

class CommentForm(FlaskForm):
    content = TextAreaField('Comment', validators=[DataRequired(), Length(max=200)])
    submit = SubmitField('Comment')

class ProfileForm(FlaskForm):
    avatar = StringField('Avatar URL', validators=[Optional(), URL()])
    bio = TextAreaField('Bio', validators=[Optional(), Length(max=500)])
    submit = SubmitField('Update Profile')

class CategoryForm(FlaskForm):
    name = StringField('Category Name', validators=[DataRequired(), Length(max=50)])
    submit = SubmitField('Add Category')
