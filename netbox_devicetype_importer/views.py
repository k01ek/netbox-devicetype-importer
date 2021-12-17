from collections import OrderedDict
from urllib.parse import urlencode


from django.conf import settings
from django.db import transaction
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.views.generic import View
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, reverse
from django.utils.text import slugify

from netbox.views import generic
from dcim.models import Manufacturer, DeviceType
from dcim import forms
from utilities.views import ContentTypePermissionRequiredMixin
from utilities.forms import ImportForm, restrict_form_fields
from utilities.exceptions import AbortTransaction, PermissionsViolation

from .models import MetaDeviceType
from .tables import MetaDeviceTypeTable
from .filters import MetaDeviceTypeFilterSet
from .forms import MetaDeviceTypeFilterForm
from .utilities import GitHubAPI, GitHubGQLAPI, GQLError


class MetaDeviceTypeListView(generic.ObjectListView):
    queryset = MetaDeviceType.objects.all()
    filterset = MetaDeviceTypeFilterSet
    filterset_form = MetaDeviceTypeFilterForm
    table = MetaDeviceTypeTable
    action_buttons = ()
    template_name = 'netbox_devicetype_importer/metadevicetype_list.html'


class MetaDeviceTypeLoadView(ContentTypePermissionRequiredMixin, View):
    def get_required_permission(self):
        return 'netbox_devicetype_importer.add_metadevicetype'

    def post(self, request):
        loaded = 0
        created = 0
        updated = 0
        # deleted = 0
        if not request.user.has_perm('netbox_devicetype_importer.add_metadevicetype'):
            return HttpResponseForbidden()
        plugin_settings = settings.PLUGINS_CONFIG.get('netbox_devicetype_importer', {})
        token = plugin_settings.get('github_token')
        use_gql = plugin_settings.get('use_gql')
        repo = plugin_settings.get('repo')
        owner = plugin_settings.get('repo_owner')
        if token and use_gql:
            gh_api = GitHubGQLAPI(token=token, owner=owner, repo=repo)
        else:
            # gql only
            # gh_api = GitHubAPI(token=token, owner=owner, repo=repo)
            gh_api = GitHubGQLAPI(token=token, owner=owner, repo=repo)
        try:
            models = gh_api.get_tree()
        except GQLError as e:
            messages.error(request, message=f'GraphQL API Error: {e.message}')
            return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')

        for vendor, models in models.items():
            for model, model_data in models.items():
                loaded += 1
                try:
                    metadevietype = MetaDeviceType.objects.get(vendor=vendor, name=model)
                    if metadevietype.sha != model_data['sha']:
                        metadevietype.is_new = True
                        # catch save exception
                        metadevietype.save()
                        updated += 1
                    else:
                        metadevietype.is_new = False
                        metadevietype.save()
                    continue
                except ObjectDoesNotExist:
                    # its new
                    metadevietype = MetaDeviceType.objects.create(
                        vendor=vendor,
                        name=model,
                        sha=model_data['sha']
                    )
                    created += 1
        messages.success(request, f'Loaded: {loaded}, Created: {created}, Updated: {updated}')
        return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')


class MetaDeviceTypeImportView(ContentTypePermissionRequiredMixin, View):
    queryset = MetaDeviceType.objects.all()
    filterset = MetaDeviceTypeFilterSet
    filterset_form = MetaDeviceTypeFilterForm

    related_object_forms = OrderedDict((
        ('console-ports', forms.ConsolePortTemplateImportForm),
        ('console-server-ports', forms.ConsoleServerPortTemplateImportForm),
        ('power-ports', forms.PowerPortTemplateImportForm),
        ('power-outlets', forms.PowerOutletTemplateImportForm),
        ('interfaces', forms.InterfaceTemplateImportForm),
        ('rear-ports', forms.RearPortTemplateImportForm),
        ('front-ports', forms.FrontPortTemplateImportForm),
        ('device-bays', forms.DeviceBayTemplateImportForm),
    ))

    def get_required_permission(self):
        return 'netbox_devicetype_importer.add_metadevicetype'

    def post(self, request):
        vendor_count = 0
        errored = 0
        imported_dt = []
        model = self.queryset.model

        if request.POST.get('_all'):
            if self.filterset is not None:
                pk_list = [obj.pk for obj in self.filterset(request.GET, model.objects.only('pk')).qs]
            else:
                pk_list = model.objects.values_list('pk', flat=True)
        else:
            pk_list = [int(pk) for pk in request.POST.getlist('pk')]

        plugin_settings = settings.PLUGINS_CONFIG.get('netbox_devicetype_importer', {})
        token = plugin_settings.get('github_token')
        use_gql = plugin_settings.get('use_gql')
        repo = plugin_settings.get('repo')
        owner = plugin_settings.get('repo_owner')

        if token and use_gql:
            gh_api = GitHubGQLAPI(token=token, owner=owner, repo=repo)
        else:
            # GraphQL only
            # gh_api = GitHubAPI(token=token, owner=owner, repo=repo)
            gh_api = GitHubGQLAPI(token=token, owner=owner, repo=repo)

        query_data = {}
        # check already imported mdt
        already_imported_mdt = model.objects.filter(pk__in=pk_list, is_imported=True)
        if already_imported_mdt.exists():
            for _mdt in already_imported_mdt:
                if DeviceType.objects.filter(pk=_mdt.imported_dt).exists() is False:
                    _mdt.imported_dt = None
                    _mdt.save()
        vendors_for_cre = set(model.objects.filter(pk__in=pk_list).values_list('vendor', flat=True))
        for vendor, name, sha in model.objects.filter(pk__in=pk_list, is_imported=False).values_list('vendor', 'name', 'sha'):
            query_data[sha] = f'{vendor}/{name}'
        if not query_data:
            messages.warning(request, message='Nothing to import')
            return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')
        try:
            dt_files = gh_api.get_files(query_data)
        except GQLError as e:
            dt_files = {}
            messages.error(request, message=f'GraphQL API Error: {e.message}')
            return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')
        # cre manufacturers
        for vendor in vendors_for_cre:
            manu, _ = Manufacturer.objects.get_or_create(name=vendor, slug=slugify(vendor))
            if _:
                vendor_count += 1

        for sha, yaml_text in dt_files.items():
            form = ImportForm(data={'data': yaml_text, 'format': 'yaml'})
            if form.is_valid():
                data = form.cleaned_data['data']
                model_form = forms.DeviceTypeImportForm(data)
                # is it nessescary?
                restrict_form_fields(model_form, request.user)

                for field_name, field in model_form.fields.items():
                    if field_name not in data and hasattr(field, 'initial'):
                        model_form.data[field_name] = field.initial

                if model_form.is_valid():
                    try:
                        with transaction.atomic():
                            obj = model_form.save()

                            for field_name, related_object_form in self.related_object_forms.items():
                                related_obj_pks = []
                                for i, rel_obj_data in enumerate(data.get(field_name, list())):
                                    f = related_object_form(obj, rel_obj_data)
                                    for subfield_name, field in f.fields.items():
                                        if subfield_name not in rel_obj_data and hasattr(field, 'initial'):
                                            f.data[subfield_name] = field.initial
                                    if f.is_valid():
                                        related_obj = f.save()
                                        related_obj_pks.append(related_obj.pk)
                                    else:
                                        for subfield_name, errors in f.errors.items():
                                            for err in errors:
                                                err_msg = "{}[{}] {}: {}".format(field_name, i, subfield_name, err)
                                                model_form.add_error(None, err_msg)
                                        raise AbortTransaction()
                    except AbortTransaction:
                        # log ths
                        pass
                    except PermissionsViolation:
                        errored += 1
                        continue
                if model_form.errors:
                    errored += 1
                else:
                    imported_dt.append(obj.pk)
                    metadt = MetaDeviceType.objects.get(sha=sha)
                    metadt.imported_dt = obj.pk
                    metadt.save()
            else:
                errored += 1
        # msg
        if imported_dt:
            messages.success(request, f'Imported: {imported_dt.__len__()}')
            if errored:
                messages.error(request, f'Failed: {errored}')
            qparams = urlencode({'id': imported_dt}, doseq=True)
            return redirect(reverse('dcim:devicetype_list') + '?' + qparams)
        else:
            messages.error(request, 'Can not import Device Types')
            return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')
