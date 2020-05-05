import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

class SamplerForm extends React.Component {
    constructor(props) {
        super(props);

        const initialData = {
                samplerChoice: 'dynesty',
                //number: ''
        }

        const errors = {}
        Object.keys(initialData).map((key) => {
            errors[key] = []
        })

        var data = (this.props.data !== null) ? this.props.data : initialData
        data = (this.props.state !== null) ? this.props.state : data
        this.state = {
            data: data,
            errors: errors,
            validate: false
        }

        this.forms = [
            {label: 'Sampler', name: 'samplerChoice', form: <Form.Select placeholder="Select Sampler" options={[
                {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                //{key: 'nestle', text: 'Nestle', value: 'nestle'},
                //{key: 'emcee', text: 'Emcee', value: 'emcee'},
            ]}/>},
            //{label: data.samplerChoice==='emcee' ? 'Number of Steps' : 'Number of Live Points', name: 'number', form: <Form.Input placeholder='1000'/>, errFunc: checkForErrors(isNumber, notEmpty)}
        ]
    }

    handleChange = ({name, value, errors}) => {
        this.setState(prevState => ({
            data: {
                ...prevState.data,
                [name]: value,
            },
            errors: {
                ...prevState.errors,
                [name]: errors
            }
        })) 
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        const notEmpty = (arr) => {return Boolean(arr && arr.length)}
        if (Object.values(this.state.errors).some(notEmpty)) {
            this.setState({
              ...this.state,
              validate: true  
            })
        } else {
            this.props.updateParentState(this.state.data)
            this.props.nextStep()
        }
    }

    render() {
        const {data, errors} = this.state
        return (
            <React.Fragment>
                <BaseForm data={data} errors={errors} forms={this.forms} onChange={this.handleChange} validate={this.state.validate}/>
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

// export default SamplerForm;
export default createFragmentContainer(SamplerForm, {
    data: graphql`
        fragment SamplerForm_data on SamplerType {
            samplerChoice
            number
        }
    `
});