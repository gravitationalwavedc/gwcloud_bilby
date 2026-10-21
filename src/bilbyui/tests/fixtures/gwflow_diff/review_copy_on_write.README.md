# Review copy-on-write producer/consumer contract fixture

This is a producer/consumer contract fixture. The `producer` block records a
successful attachment-creation result for analysis `A1`, Review content `R1`,
and occurrence identity `O`.

`version_1` represents analysis `A1` being added with the `R1` attachment at
occurrence `O`. `version_2` represents analysis `A2` being added with the `R2`
attachment at the same occurrence `O`, while the cloned `A1` representation and
its unchanged `R1` attachment remain under `A2`'s `preserved_analyses` record.

Occurrence uniqueness is scoped per owning analysis revision. The composite
identities `A1/R1/O` and `A2/R2/O` therefore coexist legally: each owning
analysis has exactly one attachment at occurrence `O`.

This fixture proves that the semantic-diff consumer preserves both composite
identities and the cloned attachment content. It cannot prove producer-side
database uniqueness enforcement or prove independently that the recorded
producer operation actually ran.
