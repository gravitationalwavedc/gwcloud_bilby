import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty} from "../../Utils/errors";



class SamplerForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
                samplerChoice: 'dynesty',
                number: ''
            },

            errors: {
                samplerChoice: [],
                number: [],
            },

            validate: false
        }
        this.state.data = this.props.state === null ? this.state.data : this.props.state
    }

    handleChange = (e, data) => {
        this.setState({
            ...this.state,
            data: {
                ...this.state.data,
                [data.name]: data.type === "checkbox" ? data.checked : data.value,
            },
        })
    }

    checkErrors = (name, value) => {
        let errors = []
        switch (name) {
            case 'number':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
        }
        return errors;
    }

    handleErrors = () => {
        let {data, errors} = this.state
        for (const [name, val] of Object.entries(data)) {
            errors[name] = this.checkErrors(name, val)
        }
        this.setState({
            ...this.state,
            errors: errors
        })
    }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        this.handleErrors()
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
                <BaseForm onChange={this.handleChange} validate={this.state.validate}
                    forms={[
                        {rowName: 'Sampler', form: <Form.Select name='samplerChoice' placeholder="Select Sampler" value={data.samplerChoice} options={[
                            {key: 'dynesty', text: 'Dynesty', value: 'dynesty'},
                            {key: 'nestle', text: 'Nestle', value: 'nestle'},
                            {key: 'emcee', text: 'Emcee', value: 'emcee'},
                        ]}/>},
                        {rowName: data.samplerChoice==='emcee' ? 'Number of Steps' : 'Number of Live Points', form: <Form.Input name='number' placeholder='1000' value={data.number}/>, errors: errors.number}
                    ]}
                />
                <Grid.Row columns={2}>
                    <Grid.Column floated='left'>
                        <Button onClick={this.prevStep}>Back</Button>
                    </Grid.Column>
                    <Grid.Column floated='right'>
                        <Button onClick={this.nextStep}>Continue</Button>
                    </Grid.Column>
                </Grid.Row>
            </React.Fragment>
        )
    }
}

export default SamplerForm;