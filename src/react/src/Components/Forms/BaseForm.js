import React from "react";
import { Form, Grid } from "semantic-ui-react";
import { FormController, InputField, TextField, CheckboxField } from "./Forms";
import { StepPage } from "../Utils/Steps";


function BaseForm(props) {

    return (
        <Grid>
            <Grid.Row>
                <Form>
                    <FormController {...props.formProps}>
                        {({values, handleSubmit}) => {
                            return (
                                <Grid textAlign='left'>
                                    <Grid.Row columns={3} verticalAlign="bottom" >
                                        <Grid.Column width={3}/> {/*Spacing*/}
                                        <Grid.Column width={8}>
                                            <InputField placeholder='Name of your job...' name='start.name' size="massive"/>
                                            <TextField placeholder='Describe your job...' name='start.description' />
                                        </Grid.Column>
                                        <Grid.Column width={2}>
                                            <CheckboxField label='Private' name='start.private' toggle />
                                        </Grid.Column>
                                    </Grid.Row>
                                    <StepPage onChangeForm={handleSubmit}>
                                        {props.setForms(values)}
                                    </StepPage>
                                </Grid>
                            )
                        }}
                    </FormController>
                </Form>
            </Grid.Row>
        </Grid>
    )
}

export default BaseForm