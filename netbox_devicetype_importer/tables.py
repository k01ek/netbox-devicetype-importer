from utilities.tables import BaseTable, ToggleColumn

from .models import MetaDeviceType


class MetaDeviceTypeTable(BaseTable):
    pk = ToggleColumn()
    id = None

    def render_name(self, value):
        return '{}'.format(value.split('.')[0])

    class Meta(BaseTable.Meta):
        model = MetaDeviceType
        fields = ('pk', 'name', 'vendor', 'is_new', 'is_imported')
        default_columns = ('pk', 'name', 'vendor', 'is_imported')
