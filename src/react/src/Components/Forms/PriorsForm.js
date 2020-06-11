import React from "react";
import {FormController, FormField} from "./Forms";
import {Grid, Button, Form} from "semantic-ui-react";

import { graphql, createFragmentContainer } from "react-relay";

class PriorsForm extends React.Component {
    constructor(props) {
        super(props);
        this.formController = React.createRef();
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        this.formController.current.setValidating()
        if (this.formController.current.state.isValid) {
            this.props.updateParentState(this.formController.current.state.values)
            this.props.nextStep()
        }
    }

    setForms(values) {

        const forms = [
            {
                label: 'Default Prior',
                name: 'priorChoice',
                form: <Form.Select placeholder="Select Default Prior" options={
                    [
                        {key: '4s', text: '4s', value: '4s'},
                        {key: '8s', text: '8s', value: '8s'},
                        {key: '16s', text: '16s', value: '16s'},
                        {key: '32s', text: '32s', value: '32s'},
                        {key: '64s', text: '64s', value: '64s'},
                        {key: '128s', text: '128s', value: '128s'},
                    ]
                }/>
            }
        ]
        
        return forms
    }

    render() {
        var initialData = {
            priorChoice: '4s'
        }

        initialData = (this.props.data !== null) ? this.props.data : initialData
        initialData = (this.props.state !== null) ? this.props.state : initialData

        return (
            <React.Fragment>
                <FormController
                    initialValues={initialData}
                    ref={this.formController}
                >
                    {
                        props => {
                            return (
                                <Grid.Row>
                                    <Grid.Column width={10}>
                                        <Form>
                                            <Grid textAlign='left'>
                                                {
                                                    this.setForms(props.values).map(
                                                        (form, index) => (<FormField key={index} {...form}/>)
                                                    )
                                                }
                                            </Grid>
                                        </Form>
                                    </Grid.Column>
                                </Grid.Row>
                            )
                        }
                    }
                </FormController>
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Save and Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default createFragmentContainer(PriorsForm, {
    data: graphql`
        fragment PriorsForm_data on PriorType {
            priorChoice
        }
    `
});