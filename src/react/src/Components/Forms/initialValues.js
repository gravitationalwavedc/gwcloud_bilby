const initialValues = {
    // Job Details
    name: 'Untitled',
    description: 'A good description is specific, unique, and memorable.',
    private: true,
    // Data Page
    dataChoice: 'real',
    triggerTime: 1126259462.391,
    samplingFrequency: '512',
    signalDuration: '4',
    eventId: null,
    // Handford Detector
    hanford: false,
    hanfordChannel: 'GWOSC',
    hanfordMinimumFrequency: 20,
    hanfordMaximumFrequency: 1024,
    // Virgo Detector
    virgo: false,
    virgoChannel: 'GWOSC',
    virgoMinimumFrequency: 20,
    virgoMaximumFrequency: 1024,
    // Livingston Detector
    livingston: false,
    livingstonChannel: 'GWOSC',
    livingstonMinimumFrequency: 20,
    livingstonMaximumFrequency: 1024,

    // Signal Page
    signalChoice: 'skip',
    mass1: 30,
    mass2: 25,
    luminosityDistance: 2000,
    mergerTime: 1126259642.413,
    psi: 0.4,
    iota: 2.659,
    phase: 1.3,
    ra: 1.375,
    dec: -1.2108,

    // Priors
    priorChoice: '4s',

    // Sampler
    sampler: 'dynasty',
    nlive: 1000,
    nact: 10,
    maxmcmc: 5000,
    walks: 1000,
    dlogz: 0.1,
};

export default initialValues;
