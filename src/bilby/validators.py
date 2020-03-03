from django.core.exceptions import ValidationError
from django.utils.translation import gettext_lazy as _

def validate_boolean_string(value):
    if value not in ['false', 'False', 'true', 'True']:
        raise ValidationError(_('%(value)s is not a boolean string'))

def validate_float_string(value):
    try:
        float(value)
        print(value, float(value))
    except:
        raise ValidationError(_('%(value)s cannot be converted to float'), params={'value': value})