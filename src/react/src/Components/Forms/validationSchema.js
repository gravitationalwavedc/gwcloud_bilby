import * as Yup from 'yup';

let validationSchema = Yup.object().shape({
    name: Yup.string()
        .min(5, 'Make the title longer than 5 characters.')
        .max(30, 'Make the title less than 30 characters.')
        .matches(/^[0-9a-z\_\-]+$/i, 'Remove any spaces or special characters.')
        .required(),
    triggerTime: Yup.number().required(),
    hanfordMinimumFrequency: Yup.number()
        .max(Yup.ref('hanfordMaximumFrequency'), 'This should be less than maximum frequency.')
        .required(),
    hanfordMaximumFrequency: Yup.number()
        .min(Yup.ref('hanfordMinimumFrequency'), 'This should be greater than minimum frequency.')
        .required(),
    hanfordChannel: Yup.string().required(),
    virgoMinimumFrequency: Yup.number()
        .max(Yup.ref('virgoMaximumFrequency'), 'This should be less than maximum frequency.').required(),
    virgoMaximumFrequency: Yup.number()
        .min(Yup.ref('virgoMinimumFrequency'),  'This should be greater than minimum frequency.').required(),
    virgoChannel: Yup.string().required(),
    livingstonMinimumFrequency: Yup.number()
        .max(Yup.ref('livingstonMaximumFrequency'), 'This should be less than maximum frequency.').required(),
    livingstonMaximumFrequency: Yup.number()
        .min(Yup.ref('livingstonMinimumFrequency'), 'This should be greater than minimum frequency.').required(),
    livingstonChannel: Yup.string().required(),
    mass1: Yup.number().min(Yup.ref('mass2')).required(),
    mass2: Yup.number().max(Yup.ref('mass1')).required(),
    luminosityDistance: Yup.number().required(),
    psi: Yup.number().required(),
    iota: Yup.number().required(),
    phase: Yup.number().required(),
    mergerTime: Yup.number().required(),
    ra: Yup.number().required(),
    dec: Yup.number().required(),
    nlive: Yup.number().min(100).integer().required(),
    nact: Yup.number().positive().required(),
    maxmcmc: Yup.number().positive().required(),
    walks: Yup.number().positive().required(),
    dlogz: Yup.number().positive().required(),
});

validationSchema = validationSchema.test(
    'activeDetectorTest',
    null,
    (obj) => {
        if ( obj.hanford || obj.virgo || obj.livingston ) {
            return true;
        }

        return new Yup.ValidationError(
            'Choose at least 1 detector.',
            null,
            'activeDetectorTest'
        );
    }
);



export default validationSchema;
