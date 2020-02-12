import React from "react";
import {Grid, Container, Image, Message, Step} from "semantic-ui-react";
import Link from 'found/lib/Link';
import {commitMutation} from "relay-runtime";
import {harnessApi} from "../index";
import {graphql} from "graphql";

import StepForm from "../Components/StepForm";

class BilbyJobForm extends React.Component {
    constructor() {
        super();

        this.state = {
            message: "No response yet",
            step: 1
        };

        commitMutation(harnessApi.getEnvironment("bilby"), {
            mutation: graphql`mutation HelloAgainMutation($input: HelloInput!)
                {
                  hello(input: $input) 
                  {
                    result
                  }
                }`,
            variables: {
                input: {
                    message: "Message to the server!"
                }
            },
            onCompleted: (response, errors) => {
                this.setState({
                    ...this.state,
                    message: response.result
                })
            },
        });
    }

    render() {
        return (
            <Grid textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                <StepForm />
            </Grid>
        )
    }
}

export default BilbyJobForm;