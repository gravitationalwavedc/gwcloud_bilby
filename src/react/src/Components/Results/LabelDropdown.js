import React, { useState, useEffect, useRef } from 'react';
import { createFragmentContainer, commitMutation, graphql } from 'react-relay';
import { HiOutlinePlus } from 'react-icons/hi';
import { Row, Col, Dropdown, Button } from 'react-bootstrap';
import { harnessApi } from '../../index';
import LabelBadge from './LabelBadge';

const CustomToggle = React.forwardRef(({ children, onClick }, ref) => (
    <Button 
        variant="link"
        className="p-0"
        ref={ref}
        onClick={e => onClick(e)}
    >
        {children}
        <HiOutlinePlus/>
    </Button>
  ));

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

    const labelChoices = props.data.allLabels.filter((l) => (!labels.includes(l.name) && !l.protected));
    return (
        <Row className="mb-1">
            {
                labels.length > 0 && 
                <Col md="auto" className="my-auto">
                    {
                        labels.map(
                            name => 
                                <LabelBadge 
                                    key={name}
                                    name={name}
                                    dismissable={props.modifiable}
                                    onDismiss={() => setLabels(labels.filter(label => label !== name))}
                                />
                        )
                    }
                </Col>
            }
            {(labelChoices.length > 0 && props.modifiable) &&
            <Col className="my-auto">
                <Dropdown>
                    <Dropdown.Toggle as={CustomToggle} id="labelControl">
                        Add label
                    </Dropdown.Toggle>
                    <Dropdown.Menu>
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
                    </Dropdown.Menu>
                </Dropdown>
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
            callback(true, 'Job labels updated!');
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
                protected
            }
        }
    `
});
