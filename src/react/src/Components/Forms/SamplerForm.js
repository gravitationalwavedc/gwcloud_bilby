import React from "react";
import {FormController, FormField} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

class SamplerForm extends React.Component {
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
                label: 'Sampler',
                name: 'samplerChoice',
                form: <Form.Select placeholder="Select Sampler" options={[
                    {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                ]}/>
            },
        ]
        
        return forms
    }

    render() {
        var initialData = {
            samplerChoice: 'dynesty'
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

export default createFragmentContainer(SamplerForm, {
    data: graphql`
        fragment SamplerForm_data on SamplerType {
            samplerChoice
            number
        }
    `
});