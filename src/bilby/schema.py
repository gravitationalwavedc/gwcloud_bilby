import graphene
from graphene import ObjectType

from graphql_jwt.decorators import login_required


class UserDetails(ObjectType):
    username = graphene.String()


class Query(object):
    gwclouduser = graphene.Field(UserDetails)

    @login_required
    def resolve_gwclouduser(self, info, **kwargs):
        return info.context.user


class Hello(graphene.relay.ClientIDMutation):
    class Input:
        message = graphene.String(required=True)

    result = graphene.String()

    @classmethod
    def mutate_and_get_payload(cls, *args, **kwargs):
        return Hello(kwargs['message'])


class Mutation(graphene.ObjectType):
    hello = Hello.Field()
