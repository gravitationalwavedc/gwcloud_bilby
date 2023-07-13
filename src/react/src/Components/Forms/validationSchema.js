import * as Yup from 'yup';

let validationSchema = Yup.object().shape({
    name: Yup.string()
        .min(5, 'Make the title longer than 5 characters.')
        .max(30, 'Make the title less than 30 characters.')
        // eslint-disable-next-line no-useless-escape
        .matches(/^[0-9a-z\_\-]+$/i, 'Remove any spaces or special characters.')
        .required(),
    triggerTime: Yup.number().required(),
    hanfordMinimumFrequency: Yup.number()
        .max(Yup.ref('hanfordMaximumFrequency'), 'This should be less than maximum frequency.')
        .required(),
    hanfordMaximumFrequency: Yup.number()
        .min(Yup.ref('hanfordMinimumFrequency'), 'This should be greater than minimum frequency.')
        .required(),
    hanfordChannel: Yup.string().nullable(),
    virgoMinimumFrequency: Yup.number()
        .max(Yup.ref('virgoMaximumFrequency'), 'This should be less than maximum frequency.')
        .required(),
    virgoMaximumFrequency: Yup.number()
        .min(Yup.ref('virgoMinimumFrequency'), 'This should be greater than minimum frequency.')
        .required(),
    virgoChannel: Yup.string().nullable(),
    livingstonMinimumFrequency: Yup.number()
        .max(Yup.ref('livingstonMaximumFrequency'), 'This should be less than maximum frequency.')
        .required(),
    livingstonMaximumFrequency: Yup.number()
        .min(Yup.ref('livingstonMinimumFrequency'), 'This should be greater than minimum frequency.')
        .required(),
    livingstonChannel: Yup.string().nullable(),
    mass1: Yup.number().min(Yup.ref('mass2')),
    mass2: Yup.number().max(Yup.ref('mass1')),
    luminosityDistance: Yup.number(),
    psi: Yup.number(),
    iota: Yup.number(),
    phase: Yup.number(),
    mergerTime: Yup.number(),
    ra: Yup.number(),
    dec: Yup.number(),
    nlive: Yup.number().min(100).integer().required(),
    nact: Yup.number().positive().integer().required(),
    maxmcmc: Yup.number().positive().integer().required(),
    walks: Yup.number().positive().integer().required(),
    dlogz: Yup.number().positive().required(),
});

validationSchema = validationSchema.test('activeDetectorTest', null, (obj) => {
    if (obj.hanford || obj.virgo || obj.livingston) {
        return true;
    }

    return new Yup.ValidationError('Choose at least 1 detector.', null, 'activeDetectorTest');
});

const detectorChannelError = (object) =>
    new Yup.ValidationError(`Please choose a ${object} detector channel.`, null, 'activeDetectorChannelTest');

validationSchema = validationSchema.test('activeDetectorChannelTest', null, (obj) => {
    const detectorChannelErrors = [
        {
            name: 'hanford',
            on: obj.hanford,
            channel: obj.hanfordChannel,
        },
        {
            name: 'livingston',
            on: obj.livingston,
            channel: obj.livingstonChannel,
        },
        {
            name: 'virgo',
            on: obj.virgo,
            channel: obj.virgoChannel,
        },
    ]
        .filter((detector) => detector.on && !detector.channel)
        .map((detector) => detectorChannelError(detector.name));

    return detectorChannelErrors.length > 0 ? detectorChannelErrors[0] : true;
});

export default validationSchema;
