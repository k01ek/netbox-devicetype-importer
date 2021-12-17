from extras.plugins import PluginConfig
from .version import __version__


class NetboxdevicetypeimporterConfig(PluginConfig):
    name = 'netbox_devicetype_importer'
    verbose_name = 'DeviceType Importer'
    description = 'Import DeviceType from github repo'
    version = __version__
    author = 'Nikolay Yuzefovich'
    author_email = 'mgk.kolek@gmail.com'
    required_settings = []
    min_version = '3.0.0'
    max_version = '3.0.99'
    default_settings = {
        'repo_owner': 'netbox-community',
        'repo': 'devicetype-library',
        'github_token': '',
        'use_gql': True,
    }


config = NetboxdevicetypeimporterConfig # noqa
