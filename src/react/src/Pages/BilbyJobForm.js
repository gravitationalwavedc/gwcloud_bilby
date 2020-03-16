import React from "react";
import {Grid} from "semantic-ui-react";
import {harnessApi} from "../index";
import StepForm from "../Components/StepForm";
import { graphql, QueryRenderer } from "react-relay";

class BilbyJobForm extends React.Component {
    constructor() {
        super();
    }

    
    render() {
        return (
            <Grid centered textAlign='center' style={{height: '100vh'}} verticalAlign='middle'>
                <StepForm />
            </Grid>
        )
    }
}

export default BilbyJobForm;