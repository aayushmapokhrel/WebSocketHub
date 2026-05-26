from rest_framework import generics, status, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import get_user_model
from accounts.serializers import (
    RegisterSerializer,
    UserProfileSerializer,
    UserPublicSerializer,
    ChangePasswordSerializer,
    CustomTokenObtainPairSerializer,
)
from rest_framework.permissions import IsAuthenticated

User = get_user_model()


class RegisterView(generics.CreateAPIView):

    serializer_class = RegisterSerializer
    permission_classes = [permissions.AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "user": UserProfileSerializer(user).data,
                "tokens": {
                    "refresh": str(refresh),
                    "access": str(refresh.access_token),
                },
            },
            status=status.HTTP_201_CREATED,
        )


class LoginView(TokenObtainPairView):

    serializer_class = CustomTokenObtainPairSerializer


class LogoutView(APIView):

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception:
            return Response(
                {"detail": "Invalid token."}, status=status.HTTP_400_BAD_REQUEST
            )


class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = [IsAuthenticated] 

    serializer_class = UserProfileSerializer

    def get_object(self):
        return self.request.user


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = request.user
        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"old_password": "Incorrect password."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response({"detail": "Password updated successfully."})


class UserSearchView(generics.ListAPIView):

    serializer_class = UserPublicSerializer

    def get_queryset(self):
        q = self.request.query_params.get("q", "").strip()
        if not q:
            return User.objects.none()
        return User.objects.filter(username__icontains=q).exclude(
            id=self.request.user.id
        )[:20]


class UserDetailView(generics.RetrieveAPIView):

    serializer_class = UserPublicSerializer
    queryset = User.objects.all()
    lookup_field = "id"
