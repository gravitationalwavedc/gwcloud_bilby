from bilbyui.models import EventID


def list_event_ids_for_user(user):
    return EventID.visible_to(user)


def get_event_id(event_id, user):
    return EventID.get_by_event_id(event_id=event_id, user=user)
