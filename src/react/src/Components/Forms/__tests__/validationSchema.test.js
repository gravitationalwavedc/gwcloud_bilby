import validationSchema from '../validationSchema';

describe('validation schema', () => {
    it('should check that a detector has been selected', async () => {
        expect.hasAssertions();
        expect(() => validationSchema.validateSync()).toThrow('Choose at least 1 detector.');
    });

    it('should check that the channel and detector match', async () => {
        expect.hasAssertions();

        expect(() => validationSchema.validateSync({ hanford: true })).toThrow(
            'Please choose a hanford detector channel.',
        );
        expect(() => validationSchema.validateSync({ hanford: true, hanfordChannel: 'GWOSC' })).toThrow(
            'dlogz is a required field',
        );

        expect(() => validationSchema.validateSync({ virgo: true })).toThrow(
            'Please choose a virgo detector channel.',
        );
        expect(() => validationSchema.validateSync({ virgo: true, virgoChannel: 'GWOSC' })).toThrow(
            'dlogz is a required field',
        );

        expect(() => validationSchema.validateSync({ livingston: true })).toThrow(
            'Please choose a livingston detector channel.',
        );
        expect(() =>
            validationSchema.validateSync({
                livingston: true,
                livingstonChannel: 'GWOSC',
            }),
        ).toThrow('dlogz is a required field');
    });
});
