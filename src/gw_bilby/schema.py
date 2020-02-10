import graphene
import bilby.schema


class Query(bilby.schema.Query, graphene.ObjectType):
    pass


class Mutation(bilby.schema.Mutation, graphene.ObjectType):
    pass


schema = graphene.Schema(query=Query, mutation=Mutation)
