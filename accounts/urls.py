from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from accounts.views import (
    RegisterView, LoginView, LogoutView,
    ProfileView, ChangePasswordView,
    UserSearchView, UserDetailView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name='logout'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('change-password/', ChangePasswordView.as_view(), name='change_password'),
    path('users/search/', UserSearchView.as_view(), name='user_search'),
    path('users/<uuid:id>/', UserDetailView.as_view(), name='user_detail'),
]