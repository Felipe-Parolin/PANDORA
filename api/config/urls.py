from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import AccessGroupViewSet, CurrentUserView, EmailTokenObtainPairView, UserViewSet
from assets.views import CategoryViewSet, EquipmentViewSet, MediaAssetViewSet
from core.views import DashboardView, HealthView, NotificationViewSet
from customers.views import CustomerViewSet
from maintenance.views import MaintenancePlanViewSet, ServiceOrderViewSet
from logistics.views import TransportTaskViewSet, VehicleViewSet
from rentals.views import RentalInspectionViewSet, RentalQuoteViewSet

router = DefaultRouter()
router.register("users", UserViewSet, basename="user")
router.register("access-groups", AccessGroupViewSet, basename="access-group")
router.register("customers", CustomerViewSet, basename="customer")
router.register("categories", CategoryViewSet, basename="category")
router.register("equipment", EquipmentViewSet, basename="equipment")
router.register("media", MediaAssetViewSet, basename="media")
router.register("maintenance-plans", MaintenancePlanViewSet, basename="maintenance-plan")
router.register("service-orders", ServiceOrderViewSet, basename="service-order")
router.register("rental-quotes", RentalQuoteViewSet, basename="rental-quote")
router.register("rental-inspections", RentalInspectionViewSet, basename="rental-inspection")
router.register("vehicles", VehicleViewSet, basename="vehicle")
router.register("transport-tasks", TransportTaskViewSet, basename="transport-task")
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/health/", HealthView.as_view(), name="health"),
    path("api/dashboard/", DashboardView.as_view(), name="dashboard"),
    path("api/auth/login/", EmailTokenObtainPairView.as_view(), name="login"),
    path("api/auth/refresh/", TokenRefreshView.as_view(), name="refresh"),
    path("api/auth/me/", CurrentUserView.as_view(), name="me"),
    path("api/", include(router.urls)),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
