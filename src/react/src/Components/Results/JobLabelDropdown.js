import React, { useState, useEffect, useRef } from "react";

import { Dropdown, Header, Container } from "semantic-ui-react";
import { createFragmentContainer, commitMutation, graphql } from "react-relay";
import UpdateBilbyJob from "./mutations/UpdateBilbyJob";

function JobLabelDropdown(props) {
    const [labels, setLabels] = useState(props.data.bilbyJob.labels.map(label => {return label.name}))
    
    const isMounted = useRef()

    useEffect(() => {
        if (isMounted.current) {
            UpdateBilbyJob(
                {
                    jobId: props.jobId,
                    labels: labels
                },
                props.onUpdate
            )
        } else {
            isMounted.current = true
        }
    }, [labels])

    const allLabels = props.data.allLabels.map(({name, description}) => {
        return {
            key: name,
            text: name,
            value: name,
            content: <Header content={name} subheader={description}/>
        }
    })
    
    return <Dropdown onChange={(e, {value}) => setLabels(value)} as={Container} options={allLabels} placeholder='Add job labels...' multiple value={labels}/>
}

export default createFragmentContainer(JobLabelDropdown, {
    data: graphql`
        fragment JobLabelDropdown_data on Query @argumentDefinitions(
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
})
