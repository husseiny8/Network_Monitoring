"""
URL configuration for the account app.
"""

from django.urls import path

from account.views import (
    LoginView,
    LogoutView,
    SignUpView,
    user_form_view,
    users_view,
)

urlpatterns = [
    path("login", LoginView, name="login"),
    path("logout", LogoutView, name="logout"),
    path("signup", SignUpView, name="signup"),

    path("users", users_view, name="users"),
    path("users/new", user_form_view, name="user_create"),
    path("users/<int:user_id>/edit", user_form_view, name="user_edit"),
]
