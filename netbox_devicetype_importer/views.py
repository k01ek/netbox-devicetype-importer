from collections import OrderedDict
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponseForbidden
from django.shortcuts import redirect, reverse
from django.utils.text import slugify
from django.views.generic import View

from dcim import forms
from dcim.models import DeviceType, Manufacturer, ModuleType
from netbox.views import generic
from utilities.exceptions import AbortTransaction, PermissionsViolation
from utilities.forms import ImportForm, restrict_form_fields
from utilities.views import ContentTypePermissionRequiredMixin, GetReturnURLMixin
from .choices import TypeChoices
from .filters import MetaDeviceTypeFilterSet
from .forms import MetaDeviceTypeFilterForm
from .gql import GQLError, GitHubGqlAPI
from .models import MetaDeviceType
from .tables import MetaTypeTable


class MetaDeviceTypeListView(generic.ObjectListView):
    queryset = MetaDeviceType.objects.filter(type=TypeChoices.TYPE_DEVICE)
    filterset = MetaDeviceTypeFilterSet
    filterset_form = MetaDeviceTypeFilterForm
    table = MetaTypeTable
    actions = ()
    action_buttons = ()
    template_name = 'netbox_devicetype_importer/metadevicetype_list.html'


class MetaModuleTypeListView(generic.ObjectListView):
    queryset = MetaDeviceType.objects.filter(type=TypeChoices.TYPE_MODULE)
    filterset = MetaDeviceTypeFilterSet
    filterset_form = MetaDeviceTypeFilterForm
    table = MetaTypeTable
    actions = ()
    action_buttons = ()
    template_name = 'netbox_devicetype_importer/metamoduletype_list.html'


class GenericTypeLoadView(ContentTypePermissionRequiredMixin, GetReturnURLMixin, View):
    path = None

    def get_required_permission(self):
        return 'netbox_devicetype_importer.add_metadevicetype'

    def post(self, request):
        loaded = 0
        created = 0
        updated = 0
        return_url = self.get_return_url(request)

        if not request.user.has_perm('netbox_devicetype_importer.add_metadevicetype'):
            return HttpResponseForbidden()
        plugin_settings = settings.PLUGINS_CONFIG.get('netbox_devicetype_importer', {})
        token = plugin_settings.get('github_token')
        repo = plugin_settings.get('repo')
        branch = plugin_settings.get('branch')
        owner = plugin_settings.get('repo_owner')
        gh_api = GitHubGqlAPI(token=token, owner=owner, repo=repo, branch=branch, path=self.path)
        try:
            models = gh_api.get_tree()
        except GQLError as e:
            messages.error(request, message=f'GraphQL API Error: {e.message}')
            return redirect('plugins:netbox_devicetype_importer:metadevicetype_list')

        for vendor, models in models.items():
            for model, model_data in models.items():
                loaded += 1
                try:
                    metadevietype = MetaDeviceType.objects.get(vendor=vendor, name=model, type=self.path)
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
                    MetaDeviceType.objects.create(
                        vendor=vendor,
                        name=model,
                        sha=model_data['sha'],
                        type=self.path
                    )
                    created += 1
        messages.success(request, f'Loaded: {loaded}, Created: {created}, Updated: {updated}')
        return redirect(return_url)


class MetaDeviceTypeLoadView(GenericTypeLoadView):
    path = TypeChoices.TYPE_DEVICE


class MetaModuleTypeLoadView(GenericTypeLoadView):
    path = TypeChoices.TYPE_MODULE


class GenericTypeImportView(ContentTypePermissionRequiredMixin, GetReturnURLMixin, View):
    filterset = MetaDeviceTypeFilterSet
    filterset_form = MetaDeviceTypeFilterForm
    type = None
    type_model = None
    model_form = None
    related_object = None

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
        return_url = self.get_return_url(request)

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
        repo = plugin_settings.get('repo')
        branch = plugin_settings.get('branch')
        owner = plugin_settings.get('repo_owner')
        version_minor = settings.VERSION.split('.')[1]

        # for 3.2 new devicetype components
        if version_minor == '2':
            self.related_object_forms.popitem()
            self.related_object_forms.update(
                {
                    'module-bays': forms.ModuleBayTemplateImportForm,
                    'device-bays': forms.DeviceBayTemplateImportForm,
                    'inventory-items': forms.InventoryItemTemplateImportForm
                }
            )

        gh_api = GitHubGqlAPI(token=token, owner=owner, repo=repo, branch=branch, path=self.type)

        query_data = {}
        # check already imported mdt
        already_imported_mdt = model.objects.filter(pk__in=pk_list, is_imported=True, type=self.type)
        if already_imported_mdt.exists():
            for _mdt in already_imported_mdt:
                if self.type_model.objects.filter(pk=_mdt.imported_dt).exists() is False:
                    _mdt.imported_dt = None
                    _mdt.save()
        vendors_for_cre = set(model.objects.filter(pk__in=pk_list).values_list('vendor', flat=True))
        for vendor, name, sha in model.objects.filter(pk__in=pk_list, is_imported=False).values_list(
            'vendor', 'name', 'sha'
        ):
            query_data[sha] = f'{vendor}/{name}'
        if not query_data:
            messages.warning(request, message='Nothing to import')
            return redirect(return_url)
        try:
            dt_files = gh_api.get_files(query_data)
        except GQLError as e:
            messages.error(request, message=f'GraphQL API Error: {e.message}')
            return redirect(return_url)
        # cre manufacturers
        for vendor in vendors_for_cre:
            manu, created = Manufacturer.objects.get_or_create(name=vendor, slug=slugify(vendor))
            if created:
                vendor_count += 1

        for sha, yaml_text in dt_files.items():
            form = ImportForm(data={'data': yaml_text, 'format': 'yaml'})
            if form.is_valid():
                data = form.cleaned_data['data']
                model_form = self.model_form(data)
                # is it necessary?
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
                                    if version_minor == '2':
                                        rel_obj_data.update({self.related_object: obj})
                                        f = related_object_form(rel_obj_data)
                                    else:
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
            # Black magic to get the url path from the type
            return redirect(reverse(f'dcim:{str(self.type).replace("-", "").rstrip("s")}_list') + '?' + qparams)
        else:
            messages.error(request, 'Can not import Device Types')
            return redirect(return_url)


class MetaDeviceTypeImportView(GenericTypeImportView):
    queryset = MetaDeviceType.objects.filter(type=TypeChoices.TYPE_DEVICE)
    type = TypeChoices.TYPE_DEVICE
    type_model = DeviceType
    model_form = forms.DeviceTypeImportForm
    related_object = 'device_type'


class MetaModuleTypeImportView(GenericTypeImportView):
    queryset = MetaDeviceType.objects.filter(type=TypeChoices.TYPE_MODULE)
    type = TypeChoices.TYPE_MODULE
    type_model = ModuleType
    model_form = forms.ModuleTypeImportForm
    related_object = 'module_type'
