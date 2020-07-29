import React from "react";
import { Message } from "semantic-ui-react";
import { createFragmentContainer, graphql } from "react-relay";
import statusColours from "../../Utils/statusColours";

function JobStatusMessage({ status }) {
    const { number, name, date } = status.jobStatus

    return <Message className={statusColours[number]} compact header={'Status: ' + name} content={date} />
}

export default createFragmentContainer(JobStatusMessage, {
    status: graphql`
        fragment JobStatusMessage_status on BilbyJobNode {
            jobStatus {
                name
                number
                date
            }
        }
    `
})
