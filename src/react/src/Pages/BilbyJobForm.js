import React from "react";
import {Grid, Container, Image, Message, Step} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
// import {graphql} from "graphql";

import StepForm from "../Components/StepForm";
import { graphql, QueryRenderer } from "react-relay";

class BilbyJobForm extends React.Component {
    constructor() {
        super();

        this.state = {
            message: "No response yet",
            step: 1
        };
    }

    renderForms = ({error, props}) => {
        if (error) {
            return <div>{error.message}</div>
        } else if (props) {
            return (
                <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                    <StepForm />
                </Grid>
            )
        }
    }
    
    render() {
        return (
            <QueryRenderer
                environment={harnessApi.getEnvironment('bilby')}
                query={graphql`
                    query BilbyJobFormQuery($jobID: String!) {
                        bilbyJob(jobId: $jobID) {
                            name
                        }
                    }
                `}
                variables={{
                    jobID: "1",
                }}
                render={this.renderForms}
            />
        )
    }
}

export default BilbyJobForm;