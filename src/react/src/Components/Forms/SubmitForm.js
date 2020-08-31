import React from "react";
import {Grid, Button, Message, Segment, Header} from "semantic-ui-react";
import * as Enumerable from "linq";
import { StepPage } from "../Utils/Steps";
import JobParameters from "../Results/JobParameters";

function SubmitForm(props) {
    let errors = null;
    if (props.errors)
        errors = Enumerable.from(props.errors).select((e, i) => (
            <Message error key={i}>
                {e.message}
            </Message>
        )) 

    return (
        <Grid>
            <Grid.Row columns={2}>
                <Grid.Column width={3}/>
                <Grid.Column width={10}>
                    <Header size="huge" content={props.state.start.name} subheader={props.state.start.description} />
                </Grid.Column>
            </Grid.Row>
            <StepPage submitButton={<Button onClick={props.onSubmit} content='Submit Job'/>}>
                <JobParameters bilbyJobParameters={null} parameters={props.state} />
            </StepPage>
            {
                props.errors ? (
                    <Grid.Row>
                        {errors}
                    </Grid.Row>
                ) : null
            }
        </Grid>
    )
}


export default SubmitForm;