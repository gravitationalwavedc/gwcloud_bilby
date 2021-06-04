import React from 'react';
import {graphql, createFragmentContainer} from 'react-relay';
import NewJob from '../../Pages/NewJob';

const DuplicateJobForm = (props) => {
    const jobData = props.data.bilbyJob;
    const initialValues = Object.keys(jobData).reduce((result, key) => {
        Object.keys(jobData[key]).map((item) => {
            result[item] = jobData[key][item];
        });
        return result;
    }, {});
    initialValues['name'] = `Copy-of-${initialValues.name}`;
    initialValues['description'] = `A duplicate job of ${initialValues.name}. Original description: ${initialValues.description}`;
    return <NewJob initialValues={initialValues} {...props}/>;
};

export default createFragmentContainer(DuplicateJobForm,
    {
 //       data: graphql`
 //       fragment DuplicateJobForm_data on Query @argumentDefinitions(
 //           jobId: {type: "ID!"}
 //       ){
 //           bilbyJob (id: $jobId){
 //          }
 //       }`
    }
);
