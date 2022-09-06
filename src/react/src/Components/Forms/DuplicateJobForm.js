import React from 'react';
import {graphql, createFragmentContainer} from 'react-relay';
import NewJob from '../../Pages/NewJob';
import parseJobParams from '../../Utils/ParseJobParams';

const DuplicateJobForm = (props) => {
    const params = props.data.bilbyJob.params;

    const initialValues = parseJobParams(params);

    initialValues['name'] = `Copy-of-${initialValues.name}`;
    initialValues['description'] = `A duplicate job of ${initialValues.name}. Original description: ${initialValues.description}`;

    return <NewJob initialValues={initialValues} {...props}/>;
};

export default createFragmentContainer(DuplicateJobForm,
    {
        data: graphql`
        fragment DuplicateJobForm_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ){
            bilbyJob (id: $jobId){
                params {
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
           }
           
           ...DataForm_data
        }`
    }
);
