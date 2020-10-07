import React, { useState, useEffect, useRef } from 'react';
import { createFragmentContainer, commitMutation, graphql } from 'react-relay';
import { Row, Col, DropdownButton, Dropdown, Alert } from 'react-bootstrap';
import { harnessApi } from '../../index';
import getBadgeType from '../getBadgeType';

const LabelDropdown = (props) => {
    const [labels, setLabels] = useState(props.data.bilbyJob.labels.map(label => label.name));
    
    const isMounted = useRef();

    useEffect(() => {
        if (isMounted.current) {
            updateJob(
                {
                    jobId: props.jobId,
                    labels: labels
                },
                props.onUpdate
            );
        } else {
            isMounted.current = true;
        }
    }, [labels]);

    const labelChoices = props.data.allLabels.filter(({name}) => !labels.includes(name));
    return (
        <Row>
            {labels.map(name => <Col key={name}>
                <Alert 
                    variant={getBadgeType(name)} 
                    key={name} 
                    onClose={() => setLabels(labels.filter(label => label !== name))} 
                    dismissible 
                    className="mr-1">
                    {name}
                </Alert>
            </Col>)}
            {labelChoices.length > 0 &&
          <Col>
              <DropdownButton id="labelControl" title="Add a job label" variant="outline-primary" size="lg">
                  {labelChoices.map(
                      ({name, description}) => 
                          <Dropdown.Item 
                              key={name} 
                              value={name} 
                              onClick={() => setLabels([name, ...labels])}
                          >
                              <h6>{name}</h6>
                              <p>{description}</p>
                          </Dropdown.Item>)}
              </DropdownButton>
          </Col>
            }
        </Row>
    );
};

const updateJob = (variables, callback) => commitMutation(harnessApi.getEnvironment('bilby'), {
    mutation: graphql`mutation LabelDropdownMutation($jobId: ID!, $private: Boolean, $labels: [String])
            {
              updateBilbyJob(input: {jobId: $jobId, private: $private, labels: $labels}) 
              {
                result
              }
            }`,
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
            callback(true, response.updateBilbyJob.result);
        }
    },
});


export default createFragmentContainer(LabelDropdown, {
    data: graphql`
        fragment LabelDropdown_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ) {
            bilbyJob(id: $jobId) {
                labels {
                    name
                }
            }

            allLabels {
                name
                description
            }
        }
    `
});
