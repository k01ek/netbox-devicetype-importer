from django.urls import path


from .views import MetaDeviceTypeListView, MetaDeviceTypeLoadView, MetaDeviceTypeImportView

urlpatterns = [
    path('meta-device-types/', MetaDeviceTypeListView.as_view(), name='metadevicetype_list'),
    path('meta-device-types/load/', MetaDeviceTypeLoadView.as_view(), name='metadevicetype_load'),
    path('meta-device-types/import/', MetaDeviceTypeImportView.as_view(), name='metadevicetype_import')
]
