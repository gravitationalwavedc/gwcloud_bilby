import React, { useState } from 'react';
import { harnessApi } from '../../index';
import { commitMutation, createFragmentContainer, graphql } from 'react-relay';
import { Form } from 'react-bootstrap';

const PrivacyToggle = (props) => {
    const [isPrivate, setIsPrivate] = useState(props.data.private);
    
    const handleChange = () => {
        const newValue = !isPrivate;
        setIsPrivate(newValue);
        updateJob(
            {
                jobId: props.jobId,
                private: newValue,
            },
            props.onUpdate
        );
    };

    const label = props.data.isLigoJob ? 'Share with LVK collaborators' : 'Share publicly';
    
    return props.modifiable && <Form.Group controlId="privateToggle">
        <Form.Check
            type="checkbox"
            label={label}
            onChange={handleChange} 
            checked={!isPrivate}/>
    </Form.Group>;
};

const updateJob = (variables, callback) => commitMutation(harnessApi.getEnvironment('bilby'), {
    mutation: graphql`
      mutation PrivacyToggleMutation($jobId: ID!, $private: Boolean, $labels: [String]) {
        updateBilbyJob(input: {jobId: $jobId, private: $private, labels: $labels}) {
          result
        }
      }
    `,
    optimisticResponse: {
        updateBilbyJob: {
            result: 'Job saved!'
        }
    },
    variables: variables,
    onCompleted: (response, errors) => {
        if (errors) {
            callback(false, errors);
        }
        else {
            callback(true, 'Job privacy updated!');
        }
    },
});

export default createFragmentContainer(PrivacyToggle, {
    data: graphql`
        fragment PrivacyToggle_data on BilbyJobNode {
            private
            isLigoJob
        }
    `
});




