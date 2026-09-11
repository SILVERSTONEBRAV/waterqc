# CompanyInfo/serializers.py
from rest_framework import serializers
from .models import CompanyInfo, RegionalInfo, ZonalInfo, SubZonalInfo


class SubZonalInfoSerializer(serializers.ModelSerializer):
    class Meta:
        model = SubZonalInfo
        fields = [
            "id",
            "name",
            "slug",
            "address",
            "coordinates",
            "boundary",
            "created_at",
            "updated_at",
            "zone",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class ZonalInfoSerializer(serializers.ModelSerializer):
    sub_zones = SubZonalInfoSerializer(many=True, read_only=True)

    class Meta:
        model = ZonalInfo
        fields = [
            "id",
            "name",
            "slug",
            "address",
            "coordinates",
            "boundary",
            "created_at",
            "updated_at",
            "region",
            "sub_zones",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class RegionalInfoSerializer(serializers.ModelSerializer):
    zones = ZonalInfoSerializer(many=True, read_only=True)

    class Meta:
        model = RegionalInfo
        fields = [
            "id",
            "name",
            "slug",
            "address",
            "office_location",
            "telephone_number",
            "coordinates",
            "boundary",
            "created_at",
            "updated_at",
            "company",
            "zones",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]


class CompanyInfoSerializer(serializers.ModelSerializer):
    regions = RegionalInfoSerializer(many=True, read_only=True)

    class Meta:
        model = CompanyInfo
        fields = [
            "id",
            "name",
            "slug",
            "address",
            "location",
            "phone_number",
            "telephone",
            "motto",
            "logo",
            "coordinates",
            "created_at",
            "updated_at",
            "regions",
        ]
        read_only_fields = ["id", "slug", "created_at", "updated_at"]
