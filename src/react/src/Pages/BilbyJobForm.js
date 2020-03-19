import React from "react";
import {Grid, Header, Segment} from "semantic-ui-react";
import {harnessApi} from "../index";
import StepForm from "../Components/StepForm";
import { graphql, QueryRenderer } from "react-relay";

class BilbyJobForm extends React.Component {
    constructor() {
        super();
    }

    
    render() {
        return (
            <React.Fragment>
                <Header as='h2' attached='top'>Bilby Job Form</Header>
                <Segment attached>
                    <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                            <StepForm />
                    </Grid>
                </Segment>
            </React.Fragment>
        )
    }
}

export default BilbyJobForm;