"""
URL configuration for c2c_service project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path, re_path
from drf_yasg import openapi
from drf_yasg.views import get_schema_view
from rest_framework import permissions
from rest_framework.routers import DefaultRouter
from c2c_modules.viewsets import PayrateViewSet
from django.http import HttpResponse
import requests

schema_view = get_schema_view(
    openapi.Info(
        title="Contract to Cash Service",
        default_version='v1',
        description="Contract to Cash Service API",
        terms_of_service="https://www.google.com/policies/terms/",
        contact=openapi.Contact(email="tejaswini.c@matchps.com"),
        license=openapi.License(name="BSD License"),
    ),

    public=True,
    permission_classes=[permissions.AllowAny],
)

router = DefaultRouter()
router.register(r'payrate', PayrateViewSet, basename='')


admin.site.site_header = 'C2C Data Administrator'
admin.site.index_title = 'C2C API Services'
admin.site.site_title = 'C2C API Services'

def simple_response(request):
    return HttpResponse("OK", status=200)

urlpatterns = [
    path('', simple_response),
    path('swagger/', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    re_path(r'^swagger/$', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path("c2c_service/", include("c2c_modules.urls")),
    path("admin/", admin.site.urls),
    # path('api/v1/', include(router.urls)),
]