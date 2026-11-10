
from django import template

from administration.permissions import can_access_administration


register = template.Library()


@register.simple_tag
def has_administration_access(user):
    return can_access_administration(user)
