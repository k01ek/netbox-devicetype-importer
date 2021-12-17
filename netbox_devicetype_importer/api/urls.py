"""
from rest_framework import routers
from .views import MyModel1ViewSet


router = routers.DefaultRouter()
router.register('', MyModel1ViewSet)
urlpatterns = router.urls

"""
