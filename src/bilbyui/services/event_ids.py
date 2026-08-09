from bilbyui.models import EventID
from bilbyui.utils.misc import is_ligo_user


def list_event_ids_for_user(user):
    return EventID.filter_by_ligo(is_ligo=is_ligo_user(user))


def get_event_id(event_id, user):
    return EventID.get_by_event_id(event_id=event_id, user=user)
