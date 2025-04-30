# Use mysql instead of sqlite. Or don't, I'm not your dad
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": "gwcloud_bilby",
        "HOST": "localhost",
        "USER": "gwcloud_bilby",
        "PORT": 3306,
        "PASSWORD": "gwcloud_bilby_password",
    },
}


# Add a valid JWT secret from the job controller if you want to be able to query/create jobs
JOB_CONTROLLER_JWT_SECRET = "<changeme>"

# If you're running the adacs-sso auth host on the same host (localhost)
# you'll want to change the SESSION_COOKIE_NAME, otherwise the sessions
# will overwrite one another
SESSION_COOKIE_NAME = "gwcloud_bilby_session"

# Set the secret to connect to the auth host
ADACS_SSO_CLIENT_SECRET = "gwcloud_bilby_dev_secret"
