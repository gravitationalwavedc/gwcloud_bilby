import React, { useState, useEffect, useRef } from 'react';
import { createFragmentContainer, commitMutation, graphql } from 'react-relay';
import { HiOutlinePlus } from 'react-icons/hi';
import { Form, Button, Modal, Row, Col } from 'react-bootstrap';
import { Typeahead, Highlighter } from 'react-bootstrap-typeahead';
import 'react-bootstrap-typeahead/css/Typeahead.css';
import { harnessApi } from '../../index';

const EventIDDisplay = ({eventId, triggerId, nickname}) => <React.Fragment>
    {eventId && <Col md='auto'>{`Event ID: ${eventId}`}</Col>}
    {triggerId && <Col md='auto'>{`Trigger ID: ${triggerId}`}</Col>}
    {nickname && <Col md='auto'>{`Nickname: ${nickname}`}</Col>}
</React.Fragment>;

const EventIDMenuDisplay = ({eventId, triggerId, nickname, props}) => <React.Fragment>
    <h5><Highlighter search={props.text}>{`Event ID: ${eventId}`}</Highlighter></h5>
    <Highlighter search={props.text}>{`Trigger ID: ${triggerId}; Nickname: ${nickname}`}</Highlighter>
    <hr className="m-0 p-0"/>
</React.Fragment>;

const EventIDDropdown = (props) => {
    const initialEventId = props.data.bilbyJob.eventId;
    const [show, setShow] = useState(false);
    const [eventId, setEventId] = useState(initialEventId);
    const isMounted = useRef();

    useEffect(() => {
        if (isMounted.current) {
            updateJob(
                {
                    jobId: props.jobId,
                    eventId: (eventId && eventId.eventId) || ''
                },
                props.onUpdate
            );
        } else {
            isMounted.current = true;
        }
    }, [eventId]);

    return <Row className='align-items-center'>
        {eventId && <EventIDDisplay {...eventId}/>}
        {
            props.modifiable && <Button 
                variant="link" 
                className="py-0" 
                onClick={() => setShow(true)}
            >
                {(eventId && eventId.eventId === '') ? <>Add Event ID<HiOutlinePlus/></> : 'Change Event ID'}
            </Button>
        }
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
                        onChange={(event) => {
                            setEventId(event[0]);
                        }}
                        selected={eventId ? [eventId] : []}
                        options={props.data.allEventIds}
                        labelKey='eventId'
                        filterBy={['eventId', 'triggerId', 'nickname']}
                        clearButton
                        placeholder=''
                        renderMenuItemChildren={(option, props) => <EventIDMenuDisplay {...option} props={props}/>}
                    />
                </Form.Group>
            </Modal.Body>
        </Modal>
    </Row>;
    
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
    onCompleted: (_response, errors) => {
        if (errors) {
            callback(false, errors);
        }
        else {
            callback(true, 'Job Event ID updated!');
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
