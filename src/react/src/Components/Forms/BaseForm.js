import React from "react";
import { Form, Button, Grid } from "semantic-ui-react";
import { FormController, FormField } from "./Forms";

class BaseForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            valid: false,
            validating: false,
            values: null
        }
    }

    onValid = (valid, values) => {
        this.setState(() => ({
            valid: valid,
            values: values
        }))
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        this.setState(() => ({ validating: true }))
        if (this.state.valid) {
            this.props.updateParentState(this.state.values)
            this.props.nextStep()
        }
    }

    render() {

        return (
            <React.Fragment>
                <Grid.Row>
                    <Grid.Column width={10}>
                        <Form>
                            <Grid textAlign='left'>
                                <FormController
                                    initialValues={this.props.initialData}
                                    validating={this.state.validating}
                                    onValid={this.onValid}
                                >
                                    {
                                        props => {
                                            return (
                                                this.props.setForms(props.values).map(
                                                    (form, index) => (<FormField key={index} {...form} {...props} />)
                                                )
                                            )
                                        }
                                    }
                                </FormController>
                            </Grid>
                        </Form>
                    </Grid.Column>
                </Grid.Row>
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        {
                            this.props.prevStep && <Button onClick={this.prevStep}>Back</Button>
                        }
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Save and Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default BaseForm;