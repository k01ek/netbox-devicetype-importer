# for 3.2 support
try:
    from utilities.tables import BaseTable, ToggleColumn
except ImportError:
    from netbox.tables import BaseTable
    from netbox.tables.columns import ToggleColumn

from .models import MetaDeviceType


class MetaDeviceTypeTable(BaseTable):
    pk = ToggleColumn(visible=True)
    id = None

    def render_name(self, value):
        return '{}'.format(value.split('.')[0])

    class Meta(BaseTable.Meta):
        model = MetaDeviceType
        fields = ('pk', 'name', 'vendor', 'is_new', 'is_imported')
        default_columns = ('pk', 'name', 'vendor', 'is_imported')
