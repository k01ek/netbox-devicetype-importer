from django.urls import path

from . import views

urlpatterns = [
    # Device types
    path('meta-device-types/', views.MetaDeviceTypeListView.as_view(), name='metadevicetype_list'),
    path('meta-device-types/load/', views.MetaDeviceTypeLoadView.as_view(), name='metadevicetype_load'),
    path('meta-device-types/import/', views.MetaDeviceTypeImportView.as_view(), name='metadevicetype_import'),
    # Module types
    path('meta-module-types/', views.MetaModuleTypeListView.as_view(), name='metamoduletype_list'),
    path('meta-module-types/load/', views.MetaModuleTypeLoadView.as_view(), name='metamoduletype_load'),
    path('meta-module-types/import/', views.MetaModuleTypeImportView.as_view(), name='metamoduletype_import')
]
