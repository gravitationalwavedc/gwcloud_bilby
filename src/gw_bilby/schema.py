import graphene
import bilbyui.schema
import adacs_sso_plugin.schema


class Query(bilbyui.schema.Query, adacs_sso_plugin.schema.Query, graphene.ObjectType):
    pass


class Mutation(
    bilbyui.schema.Mutation, adacs_sso_plugin.schema.Mutation, graphene.ObjectType
):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
