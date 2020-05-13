import graphene
from graphene import AbstractType, ObjectType, InputObjectType, relay, Connection, Int, String, Boolean, Field
from graphene_django.types import DjangoObjectType
from graphene_django.filter import DjangoFilterConnectionField
from django_filters import FilterSet, OrderingFilter

class OutputStartType(ObjectType):
    name = String()
    description = String()

class AbstractDataType(AbstractType):
    data_type = String()
    hanford = Boolean()
    livingston = Boolean()
    virgo = Boolean()
    signal_duration = String()
    sampling_frequency = String()
    trigger_time = String()
    hanford_minimum_frequency = String()
    hanford_maximum_frequency = String()
    hanford_channel = String()
    livingston_minimum_frequency = String()
    livingston_maximum_frequency = String()
    livingston_channel = String()
    virgo_minimum_frequency = String()
    virgo_maximum_frequency = String()
    virgo_channel = String()


class AbstractSignalType(AbstractType):
    mass1 = String()
    mass2 = String()
    luminosity_distance = String()
    psi = String()
    iota = String()
    phase = String()
    merger_time = String()
    ra = String()
    dec = String()

# class AbstractPriorType(AbstractType):
#     prior = String()

class AbstractSamplerType(AbstractType):
    number = String()


# It seems priors have to be handled differently, kept running into errors with nested AbstractTypes

# class InputPriorStructureType(InputObjectType):
#     type = String()
#     value = String()
#     min = String()
#     max = String()

# class InputPriorType(InputObjectType):
#     prior = String()
#     # mass1 = Field(InputPriorStructureType)
#     # mass2 = Field(InputPriorStructureType)
#     # luminosity_distance = Field(InputPriorStructureType)
#     # psi = Field(InputPriorStructureType)
#     # iota = Field(InputPriorStructureType)
#     # phase = Field(InputPriorStructureType)
#     # merger_time = Field(InputPriorStructureType)
#     # ra = Field(InputPriorStructureType)
#     # dec = Field(InputPriorStructureType)

# class OutputPriorStructureType(ObjectType):
#     type = String()
#     value = String()
#     min = String()
#     max = String()

# class OutputPriorType(ObjectType):
#     prior = String()
#     # mass1 = Field(OutputPriorStructureType)
#     # mass2 = Field(OutputPriorStructureType)
#     # luminosity_distance = Field(OutputPriorStructureType)
#     # psi = Field(OutputPriorStructureType)
#     # iota = Field(OutputPriorStructureType)
#     # phase = Field(OutputPriorStructureType)
#     # merger_time = Field(OutputPriorStructureType)
#     # ra = Field(OutputPriorStructureType)
#     # dec = Field(OutputPriorStructureType)