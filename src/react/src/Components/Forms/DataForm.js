import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty} from "../../Utils/errors";

import { graphql, createFragmentContainer } from "react-relay";

class DataForm extends React.Component {
    constructor(props) {
        super(props);

        const initialData = {
            dataChoice: 'simulated',
            hanford: false,
            livingston: false,
            virgo: false,
            signalDuration: '',
            samplingFrequency: '',
            startTime: ''
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
            {label: 'Type of Data', name: 'dataChoice', form: <Form.Select placeholder="Select Data Type" options={[
                {key: 'simulated', text: 'Simulated', value: 'simulated'},
                {key: 'open', text: 'Open', value: 'open'}
            ]}/>},
            {label: 'Detectors', name: 'hanford', form: <Form.Checkbox label="Hanford"/>},
            {label: null, name: 'livingston', form: <Form.Checkbox label="Livingston"/>},
            {label: null, name: 'virgo', form: <Form.Checkbox label="Virgo"/>},
            {label: 'Signal Duration (s)', name: 'signalDuration', form: <Form.Input placeholder='2'/>, errFunc: checkForErrors(isNumber, notEmpty)},
            {label: 'Sampling Frequency (Hz)', name: 'samplingFrequency', form: <Form.Input placeholder='2'/>, errFunc: checkForErrors(isNumber, notEmpty)},
            {label: 'Start Time', name: 'startTime', form: <Form.Input placeholder='2.1'/>, errFunc: checkForErrors(isNumber, notEmpty)}

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

// export default DataForm;
export default createFragmentContainer(DataForm, {
    data: graphql`
        fragment DataForm_data on DataType {
            dataChoice
            hanford
            livingston
            virgo
            signalDuration
            samplingFrequency
            startTime
        }
    `
});