from bigO.users.rest.views import UserViewSet
from django.conf import settings
from django.urls import include, path
from rest_framework.routers import DefaultRouter, SimpleRouter

if settings.DEBUG:
    router = DefaultRouter()
else:
    router = SimpleRouter()

router.register("users", UserViewSet)


app_name = "rest"
urlpatterns = [
    path("", include(router.urls)),
    # Other paths (maybe ApiViews)
]
