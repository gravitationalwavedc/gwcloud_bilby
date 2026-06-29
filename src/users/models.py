from adacs_sso_plugin.models import ADACSModelUser


class User(ADACSModelUser):
    class Meta(ADACSModelUser.Meta):
        app_label = "users"
