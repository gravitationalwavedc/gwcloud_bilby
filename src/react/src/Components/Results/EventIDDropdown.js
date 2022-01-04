import React, { useState, useEffect, useRef } from 'react';
import { createFragmentContainer, commitMutation, graphql } from 'react-relay';
import { Row, Col, DropdownButton, Dropdown, Alert, Form, Button, Modal } from 'react-bootstrap';
import {Typeahead} from 'react-bootstrap-typeahead'
import 'react-bootstrap-typeahead/css/Typeahead.css';
import { harnessApi } from '../../index';

const EventIDDropdown = (props) => {
    const initialEventId = props.data.bilbyJob.eventId
    const [show, setShow] = useState(false)
    const [eventId, setEventId] = useState(initialEventId ? initialEventId : {eventId: ''});
    
    const isMounted = useRef();

    useEffect(() => {
        if (isMounted.current) {
            updateJob(
                {
                    jobId: props.jobId,
                    eventId: eventId.eventId
                },
                props.onUpdate
            );
        } else {
            isMounted.current = true;
        }
    }, [eventId]);

    return <React.Fragment>
        <Button onClick={() => setShow(true)}>Add Event ID</Button>
        <Modal
            show={show}
            onHide={() => setShow(false)}
        >
            <Modal.Header closeButton>
                <Modal.Title>
                    Event ID
                </Modal.Title>
            </Modal.Header>
            <Modal.Body>
                <Form.Group>
                    <Typeahead
                        id='event-id-select'
                        onChange={(event) => setEventId(event[0] ? event[0] : {eventId: ''})}
                        selected={[eventId.eventId]}
                        options={props.data.allEventIds}
                        labelKey='eventId'
                        clearButton
                        placeholder=''
                    />
                </Form.Group>
            </Modal.Body>
        </Modal>
    </React.Fragment>
    
};

const updateJob = (variables, callback) => commitMutation(harnessApi.getEnvironment('bilby'), {
    mutation: graphql`mutation EventIDDropdownMutation($jobId: ID!, $eventId: String)
            {
              updateBilbyJob(input: {jobId: $jobId, eventId: $eventId}) 
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


export default createFragmentContainer(EventIDDropdown, {
    data: graphql`
        fragment EventIDDropdown_data on Query @argumentDefinitions(
            jobId: {type: "ID!"}
        ) {
            bilbyJob(id: $jobId) {
                eventId {
                    eventId
                    triggerId
                    nickname
                }
            }

            allEventIds {
                eventId
                triggerId
                nickname
            }
        }
    `
});
