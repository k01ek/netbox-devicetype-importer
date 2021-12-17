"""
from rest_framework.viewsets import ModelViewSet
from netbox_devicetype_importer.models import MyModel1
from .serializers import MyModel1Serializer


class MyModel1ViewSet(ModelViewSet):
    queryset = MyModel1.objects.all()
    serializer_class = MyModel1Serializer
"""
