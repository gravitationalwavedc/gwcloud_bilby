export default function parseJobParams(params) {
    return {
        // Details
        name: params.details.name,
        description: params.details.description,
        private: params.details.private,

        // Calibration

        // Data
        dataChoice: params.data.dataChoice,
        triggerTime: params.data.triggerTime,

        // Data - Channels
        hanfordChannel: params.data.channels.hanfordChannel,
        livingstonChannel: params.data.channels.livingstonChannel,
        virgoChannel: params.data.channels.virgoChannel,

        // Detector
        hanford: params.detector.hanford,
        hanfordMinimumFrequency: params.detector.hanfordMinimumFrequency,
        hanfordMaximumFrequency: params.detector.hanfordMaximumFrequency,
        livingston: params.detector.livingston,
        livingstonMinimumFrequency: params.detector.livingstonMinimumFrequency,
        livingstonMaximumFrequency: params.detector.livingstonMaximumFrequency,
        virgo: params.detector.virgo,
        virgoMinimumFrequency: params.detector.virgoMinimumFrequency,
        virgoMaximumFrequency: params.detector.virgoMaximumFrequency,
        signalDuration: params.detector.duration,
        samplingFrequency: params.detector.samplingFrequency,

        // Injection

        // Likelihood

        // Prior
        priorChoice: params.prior.priorDefault,

        // PostProcessing

        // Sampler
        nlive: params.sampler.nlive,
        nact: params.sampler.nact,
        maxmcmc: params.sampler.maxmcmc,
        walks: params.sampler.walks,
        dlogz: params.sampler.dlogz,
        cpus: params.sampler.cpus,
        samplerChoice: params.sampler.samplerChoice,

        // Waveform
        signalChoice: params.waveform.model,
    };
}
