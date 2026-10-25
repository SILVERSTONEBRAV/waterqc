from rest_framework.permissions import DjangoModelPermissions


class ViewModelPermissions(DjangoModelPermissions):
    """Require the model's view permission for safe requests as well."""

    def get_required_permissions(self, method, model):
        permissions = super().get_required_permissions(method, model)
        if method in ("GET", "HEAD", "OPTIONS"):
            opts = model._meta
            permissions = [f"{opts.app_label}.view_{opts.model_name}"]
        return permissions
