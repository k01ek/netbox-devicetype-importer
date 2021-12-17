from extras.plugins import PluginMenuItem


menu_items = (
    PluginMenuItem(
        link='plugins:netbox_devicetype_importer:metadevicetype_list',
        link_text='DeviceType Import',
        permissions=['netbox_devicetype_importer.view_metadevicetype'],
        buttons=(
        )
    ),
)
