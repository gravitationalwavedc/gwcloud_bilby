import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty} from "../Utils/errors";



class DataForm extends React.Component {
    constructor(props) {
        super(props);

        this.state = {
            data: {
                dataChoice: 'simulated',
                hanford: false,
                livingston: false,
                virgo: false,
                signalDuration: '',
                samplingFrequency: '',
                startTime: ''
            },

            errors: {
                signalDuration: [],
                samplingFrequency: [],
                startTime: []
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
            }
        })
    }

    checkErrors = (name, value) => {
        let errors = []
        switch (name) {
            case 'signalDuration':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'samplingFrequency':
                errors = checkForErrors(isNumber, notEmpty)(value)
                break;
            case 'startTime':
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
                        {rowName: 'Type of Data', form: <Form.Select name='dataChoice' placeholder="Select Data Type" value={data.dataChoice} options={[
                            {key: 'simulated', text: 'Simulated', value: 'simulated'},
                            {key: 'open', text: 'Open', value: 'open'}
                        ]}/>},
                        {rowName: 'Detectors', form: [<Form.Checkbox key={1} name='hanford' label="Hanford" checked={data.hanford}/>,
                                                    <Form.Checkbox key={2} name='livingston' label="Livingston" checked={data.livingston}/>,
                                                    <Form.Checkbox key={3} name='virgo' label="Virgo" checked={data.virgo}/>]},
                        {rowName: 'Signal Duration (s)', form: <Form.Input name='signalDuration' placeholder='2' value={data.signalDuration}/>, errors: errors.signalDuration},
                        {rowName: 'Sampling Frequency (Hz)', form: <Form.Input name='samplingFrequency' placeholder='2' value={data.samplingFrequency}/>, errors: errors.samplingFrequency},
                        {rowName: 'Start Time', form: <Form.Input name='startTime' placeholder='2.1' value={data.startTime}/>, errors: errors.startTime}
        
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

export default DataForm;