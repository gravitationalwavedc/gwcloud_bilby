import React, {useState} from 'react';
import {createFragmentContainer, graphql} from 'react-relay';
import {Button, Col, Form, Modal, Row} from 'react-bootstrap';
import {Highlighter, Typeahead} from 'react-bootstrap-typeahead';
import 'react-bootstrap-typeahead/css/Typeahead.css';

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

const EventIDDropdown = ({eventId, data, setEventId, modifiable}) => {
    const [show, setShow] = useState(false);

    return <Row className='align-items-center'>
        {eventId && <EventIDDisplay {...eventId}/>}
        {
            modifiable && <Button
                variant="link"
                className="py-0"
                onClick={() => setShow(true)}
            >
                {eventId ? <>Change Event ID</> : 'Set Event ID'}
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
                        options={data.allEventIds}
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

export default createFragmentContainer(EventIDDropdown, {
    data: graphql`
        fragment EventIDDropdown_data on Query {
            allEventIds {
                eventId
                triggerId
                nickname
                gpsTime
            }
        }
    `
});
