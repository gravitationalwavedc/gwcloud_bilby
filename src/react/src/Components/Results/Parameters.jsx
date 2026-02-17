import { createFragmentContainer, graphql } from 'react-relay';
import ReviewJob from '../Forms/ReviewJob';
import parseJobParams from '../../Utils/ParseJobParams';

const Parameters = (props) => {
    const params = props.params;

    if (!params) {
        return (
            <p className="text-muted">
                Parameters could not be loaded for this job (e.g. invalid or missing configuration).
            </p>
        );
    }

    const result = parseJobParams(params);

    return <ReviewJob values={result} />;
};

export default createFragmentContainer(Parameters, {
    params: graphql`
        fragment Parameters_params on JobParameterOutput {
            details {
                name
                description
                private
            }
            data {
                dataChoice
                triggerTime
                channels {
                    hanfordChannel
                    livingstonChannel
                    virgoChannel
                }
            }
            detector {
                hanford
                hanfordMinimumFrequency
                hanfordMaximumFrequency
                livingston
                livingstonMinimumFrequency
                livingstonMaximumFrequency
                virgo
                virgoMinimumFrequency
                virgoMaximumFrequency
                duration
                samplingFrequency
            }
            prior {
                priorDefault
            }
            sampler {
                nlive
                nact
                maxmcmc
                walks
                dlogz
                cpus
                samplerChoice
            }
            waveform {
                model
            }
        }
    `,
});
