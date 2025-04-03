import React, { useEffect, useRef, useState } from 'react';
import { commitMutation, createFragmentContainer, graphql } from 'react-relay';
import 'react-bootstrap-typeahead/css/Typeahead.css';
import EventIDDropdown from './EventIDDropdown';
import environment from '../../environment';

const BilbyJobEventIDDropdown = (props) => {
    const [eventId, setEventId] = useState(props.data.bilbyJob.eventId);
    const isMounted = useRef();

    useEffect(() => {
        if (isMounted.current) {
            updateJob(
                {
                    jobId: props.jobId,
                    eventId: (eventId && eventId.eventId) || null,
                },
                props.onUpdate,
            );
        } else {
            isMounted.current = true;
        }
    }, [eventId]);

    return (
        <EventIDDropdown data={props.data} modifiable={props.modifiable} eventId={eventId} setEventId={setEventId} />
    );
};

const updateJob = (variables, callback) =>
    commitMutation(environment, {
        mutation: graphql`
            mutation BilbyJobEventIDDropdownMutation($jobId: ID!, $eventId: String) {
                updateBilbyJob(input: { jobId: $jobId, eventId: $eventId }) {
                    result
                }
            }
        `,
        optimisticResponse: {
            updateBilbyJob: {
                result: 'Job saved!',
            },
        },
        variables: variables,
        onCompleted: (_response, errors) => {
            if (errors) {
                callback(false, errors);
            } else {
                callback(true, 'Job Event ID updated!');
            }
        },
    });

export default createFragmentContainer(BilbyJobEventIDDropdown, {
    data: graphql`
        fragment BilbyJobEventIDDropdown_data on Query @argumentDefinitions(jobId: { type: "ID!" }) {
            bilbyJob(id: $jobId) {
                eventId {
                    eventId
                    triggerId
                    nickname
                }
            }

            ...EventIDDropdown_data
        }
    `,
});
