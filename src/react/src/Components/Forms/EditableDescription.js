import React from 'react';
import EditableText from './EditableText';
import { graphql } from 'react-relay';
import { commitMutation } from 'relay-runtime';
import {harnessApi} from '../../index';

const mutation = graphql`
    mutation EditableDescriptionMutation($input: UpdateBilbyJobMutationInput!) {
        updateBilbyJob(input: $input) {
            result
            jobId
        }
    }
`;

const handleSaveDescription = (value, jobId) => {
    const variables = {
        input: {
            jobId: jobId,
            description: value 
        }
    };

    commitMutation(harnessApi.getEnvironment('bilby'), {
        mutation: mutation,
        variables: variables,
        onCompleted: (response, errors) => {
            if (!errors) {
                console.log('saved!');
            }
        }
    });
};

const EditableDescription = ({modifiable, value, jobId}) => <React.Fragment>
    {modifiable ? 
        <EditableText 
            name="description" 
            type="textarea"
            value={value} 
            onSave={(value) => handleSaveDescription(value, jobId)} 
            viewProps={{className: 'p'}}
        /> 
        : <p>{value}</p>}
</React.Fragment>;

export default EditableDescription;
