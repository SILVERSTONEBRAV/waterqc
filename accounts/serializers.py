from rest_framework import serializers
from django.contrib.auth.models import Group, Permission
from django.contrib.auth.password_validation import validate_password
from django.utils.http import urlsafe_base64_decode
from django.utils.encoding import force_str
from django.contrib.auth.tokens import default_token_generator

from .models import CustomUser
from core.models import Section, SystemConfiguration
from t.models import TreatmentPlant
from laboratory.models import Laboratory
from core.models import validate_password_strength


# -------------------------------------------------
# SAFE CONFIG ACCESS (NO IMPORT CYCLE RISK)
# -------------------------------------------------
def get_config():
    return SystemConfiguration.objects.get_or_create(pk=1)[0]


# -------------------------------------------------
# SECTION SERIALIZER
# -------------------------------------------------
class SectionSerializer(serializers.ModelSerializer):
    user_count = serializers.IntegerField(source="users.count", read_only=True)

    class Meta:
        model = Section
        fields = "__all__"


# -------------------------------------------------
# ACCOUNT CONFIGURATION SERIALIZER
# -------------------------------------------------
class AccountConfigurationSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemConfiguration
        fields = "__all__"


# -------------------------------------------------
# TREATMENT PLANT SERIALIZER
# -------------------------------------------------
class TreatmentPlantSerializer(serializers.ModelSerializer):
    assigned_user_count = serializers.IntegerField(
        source="assigned_users.count",
        read_only=True
    )

    class Meta:
        model = TreatmentPlant
        fields = "__all__"


# -------------------------------------------------
# LABORATORY SERIALIZER
# -------------------------------------------------
class LaboratorySerializer(serializers.ModelSerializer):
    assigned_user_count = serializers.IntegerField(
        source="assigned_users.count",
        read_only=True
    )

    class Meta:
        model = Laboratory
        fields = "__all__"


# -------------------------------------------------
# GROUP SERIALIZER (FIXED RELATION COUNT)
# -------------------------------------------------
class GroupSerializer(serializers.ModelSerializer):
    user_count = serializers.SerializerMethodField()

    class Meta:
        model = Group
        fields = ["id", "name", "user_count"]

    def get_user_count(self, obj):
        return obj.user_set.count()


# -------------------------------------------------
# PERMISSION SERIALIZER
# -------------------------------------------------
class PermissionSerializer(serializers.ModelSerializer):
    content_type = serializers.StringRelatedField()

    class Meta:
        model = Permission
        fields = ["id", "name", "codename", "content_type"]


# -------------------------------------------------
# CUSTOM USER SERIALIZER
# -------------------------------------------------
class CustomUserSerializer(serializers.ModelSerializer):
    # nested read-only
    section = SectionSerializer(read_only=True)
    assigned_treatment_plant = TreatmentPlantSerializer(read_only=True)
    assigned_lab = LaboratorySerializer(read_only=True)
    groups = GroupSerializer(many=True, read_only=True)
    user_permissions = PermissionSerializer(many=True, read_only=True)

    # writable relations
    section_id = serializers.PrimaryKeyRelatedField(
        queryset=Section.objects.all(),
        source="section",
        write_only=True,
        required=False,
        allow_null=True,
    )

    assigned_treatment_plant_id = serializers.PrimaryKeyRelatedField(
        queryset=TreatmentPlant.objects.all(),
        source="assigned_treatment_plant",
        write_only=True,
        required=False,
        allow_null=True,
    )

    assigned_lab_id = serializers.PrimaryKeyRelatedField(
        queryset=Laboratory.objects.all(),
        source="assigned_lab",
        write_only=True,
        required=False,
        allow_null=True,
    )

    groups_ids = serializers.PrimaryKeyRelatedField(
        queryset=Group.objects.all(),
        many=True,
        source="groups",
        write_only=True,
        required=False,
    )

    user_permissions_ids = serializers.PrimaryKeyRelatedField(
        queryset=Permission.objects.all(),
        many=True,
        source="user_permissions",
        write_only=True,
        required=False,
    )

    # computed fields
    full_name = serializers.SerializerMethodField()
    short_name = serializers.SerializerMethodField()
    profile_picture_url = serializers.SerializerMethodField()
    is_password_expired = serializers.SerializerMethodField()
    require_password_change = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "username",
            "email",
            "first_name",
            "last_name",
            "full_name",
            "short_name",
            "mobile_number",
            "section",
            "section_id",
            "assigned_treatment_plant",
            "assigned_treatment_plant_id",
            "assigned_lab",
            "assigned_lab_id",
            "is_active",
            "is_staff",
            "password_last_set",
            "email_verified",
            "profile_picture",
            "profile_picture_url",
            "groups",
            "groups_ids",
            "user_permissions",
            "user_permissions_ids",
            "last_login",
            "date_joined",
            "failed_login_attempts",
            "is_locked",
            "mfa_enabled",
            "mfa_secret",
            "is_password_expired",
            "require_password_change",
            "password",
        ]

        extra_kwargs = {
            "password": {"write_only": True, "min_length": 8},
            "mfa_secret": {"write_only": True},
        }

    # -------------------------------------------------
    # computed methods
    # -------------------------------------------------
    def get_full_name(self, obj):
        return obj.full_name

    def get_short_name(self, obj):
        return obj.short_name

    def get_profile_picture_url(self, obj):
        request = self.context.get("request")
        if obj.profile_picture and hasattr(obj.profile_picture, "url"):
            return request.build_absolute_uri(obj.profile_picture.url) if request else obj.profile_picture.url
        return None

    def get_is_password_expired(self, obj):
        return obj.is_password_expired()

    def get_require_password_change(self, obj):
        return obj.require_password_change()

    # -------------------------------------------------
    # create/update
    # -------------------------------------------------
    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = super().create(validated_data)

        if password:
            validate_password(password, user)
            validate_password_strength(password)
            user.set_password(password)
            user.save()

        return user

    def update(self, instance, validated_data):
        password = validated_data.pop("password", None)
        user = super().update(instance, validated_data)

        if password:
            validate_password(password, user)
            validate_password_strength(password)
            user.set_password(password)
            user.save()

        return user


# -------------------------------------------------
# PASSWORD RESET REQUEST
# -------------------------------------------------
class PasswordResetRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()

    def validate_email(self, value):
        email = value.strip().lower()
        if not CustomUser.objects.filter(email=email).exists():
            raise serializers.ValidationError("User with this email does not exist.")
        return email


# -------------------------------------------------
# PASSWORD RESET CONFIRM
# -------------------------------------------------
class PasswordResetConfirmSerializer(serializers.Serializer):
    uidb64 = serializers.CharField()
    token = serializers.CharField()
    password = serializers.CharField(write_only=True, min_length=8)

    def validate(self, attrs):
        uidb64 = attrs["uidb64"]
        token = attrs["token"]
        password = attrs["password"]

        try:
            uid = force_str(urlsafe_base64_decode(uidb64))
            user = CustomUser.objects.get(pk=uid)
        except Exception:
            raise serializers.ValidationError({"detail": "Invalid reset link."})

        if not default_token_generator.check_token(user, token):
            raise serializers.ValidationError({"detail": "Invalid or expired token."})

        validate_password(password, user)
        validate_password_strength(password)

        attrs["user"] = user
        return attrs