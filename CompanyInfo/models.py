#CompanyInfo/models.py
from django.db import models
from django.utils.text import slugify


class TimestampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class CompanyInfo(TimestampedModel):
    name = models.CharField(max_length=255, default="Nairobi City Water & Sewerage Company")
    slug = models.SlugField(unique=True, blank=True)
    address = models.CharField(max_length=255)
    location = models.CharField(max_length=255)
    phone_number = models.CharField(max_length=50)
    telephone = models.CharField(max_length=50, blank=True)
    motto = models.CharField(max_length=255, blank=True)
    logo = models.ImageField(upload_to='company/logo/', null=True, blank=True)
    favicon = models.ImageField(upload_to='favicons/', blank=True)
    coordinates = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def to_geojson(self):
        return self.coordinates if self.coordinates else None

    def __str__(self):
        return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Company"
        verbose_name_plural = "Companies"


class RegionalInfo(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    address = models.CharField(max_length=255)
    office_location = models.CharField(max_length=255)
    telephone_number = models.CharField(max_length=50)
    company = models.ForeignKey(CompanyInfo, on_delete=models.CASCADE, related_name="regions")
    coordinates = models.JSONField(null=True, blank=True)
    boundary = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.company.name}-{self.name}")
        super().save(*args, **kwargs)

    def to_geojson(self):
        return self.boundary if self.boundary else None

    def __str__(self):
        return f"{self.company.name} > {self.name}" if self.company else self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Region"
        verbose_name_plural = "Regions"


class ZonalInfo(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    address = models.CharField(max_length=255)
    region = models.ForeignKey(RegionalInfo, on_delete=models.CASCADE, related_name="zones")
    coordinates = models.JSONField(null=True, blank=True)
    boundary = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.region.name}-{self.name}")
        super().save(*args, **kwargs)

    def to_geojson(self):
        return self.boundary if self.boundary else None

    def __str__(self):
        return f"{self.region.name} > {self.name}" if self.region else self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Zone"
        verbose_name_plural = "Zones"


class SubZonalInfo(TimestampedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, blank=True)
    address = models.CharField(max_length=255)
    zone = models.ForeignKey(ZonalInfo, on_delete=models.CASCADE, related_name="sub_zones")
    coordinates = models.JSONField(null=True, blank=True)
    boundary = models.JSONField(null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(f"{self.zone.name}-{self.name}")
        super().save(*args, **kwargs)

    def to_geojson(self):
        return self.boundary if self.boundary else None

    def __str__(self):
        try:
            return f"{self.zone.region.name} > {self.zone.name} > {self.name}"
        except AttributeError:
            return self.name

    class Meta:
        ordering = ['name']
        verbose_name = "Sub-Zone"
        verbose_name_plural = "Sub-Zones"
