import graphene
import bilbyui.schema


class Query(bilbyui.schema.Query, graphene.ObjectType):
    pass


class Mutation(bilbyui.schema.Mutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
