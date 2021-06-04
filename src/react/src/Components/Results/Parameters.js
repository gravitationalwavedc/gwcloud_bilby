import React from 'react';
import {createFragmentContainer, graphql} from 'react-relay';
import ReviewJob from '../Forms/ReviewJob';

const Parameters = (props) => {
    const jobData = props.jobData ? props.jobData : props.parameters;
    const values = Object.keys(jobData).reduce((result, key) => {
        if (!jobData[key])
            return {};

        Object.keys(jobData[key]).map((item) => {
            result[item] = jobData[key][item];
        });
        return result;
    }, {});

    return <ReviewJob values={values}/>;
};

export default createFragmentContainer(Parameters, {
    //jobData: graphql`
    //    fragment Parameters_jobData on BilbyJobNode {
    //    }
    //`
});
