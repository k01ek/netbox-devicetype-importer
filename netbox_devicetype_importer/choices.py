from utilities.choices import ChoiceSet


class TypeChoices(ChoiceSet):
    TYPE_DEVICE = 'device-types'
    TYPE_MODULE = 'module-types'

    CHOICES = (
        (TYPE_DEVICE, 'Devices'),
        (TYPE_MODULE, 'Modules'),
    )
