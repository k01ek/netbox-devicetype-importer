from django.db import models

from utilities.querysets import RestrictedQuerySet
from .choices import TypeChoices


class MetaDeviceType(models.Model):
	name = models.CharField(max_length=100)
	vendor = models.CharField(max_length=50)
	type = models.CharField(max_length=20, choices=TypeChoices, default=TypeChoices.TYPE_DEVICE)
	sha = models.CharField(max_length=40)
	download_url = models.URLField(null=True, blank=True)
	is_new = models.BooleanField(default=True)
	imported_dt = models.IntegerField(null=True, blank=True)
	is_imported = models.BooleanField(default=False)

	objects = RestrictedQuerySet.as_manager()

	def __str__(self):
		return self.name.split('.')[0]

	def save(self, *args, **kwargs):
		if self.imported_dt:
			self.is_imported = True
			self.is_new = False
		else:
			self.is_imported = False
		super(MetaDeviceType, self).save(*args, **kwargs)
