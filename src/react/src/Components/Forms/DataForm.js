import React from "react";
import {BaseForm} from "./Forms";
import {Form, Grid, Button, Select} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty, noneFalse} from "../../Utils/errors";
import _ from "lodash";

import {graphql, createFragmentContainer} from "react-relay";
import * as Enumerable from "linq";

class DataForm extends React.Component {
    constructor(props) {
        super(props);
        const initialData = {
            dataChoice: 'open',
            hanford: true, // This is because of an annoying bug with errors.. I may need to, once again, refactor the forms.
            livingston: false,
            virgo: false,
            signalDuration: '4',
            samplingFrequency: '16384',
            triggerTime: '',
            hanfordMinimumFrequency: '20',
            hanfordMaximumFrequency: '1024',
            hanfordChannel: 'GWOSC',
            livingstonMinimumFrequency: '20',
            livingstonMaximumFrequency: '1024',
            livingstonChannel: 'GWOSC',
            virgoMinimumFrequency: '20',
            virgoMaximumFrequency: '1024',
            virgoChannel: 'GWOSC'
        }

        const errors = {}
        Object.keys(initialData).map((key) => {
            errors[key] = []
        })

        var data = (this.props.data !== null) ? this.props.data : initialData
        data = (this.props.state !== null) ? this.props.state : data

        const channelOptions = [
            'GWOSC',
            'GDS-CALIB_STRAIN',
            'Hrec_hoft_16384Hz',
            data.hanfordChannel,
            data.livingstonChannel,
            data.virgoChannel,
        ]
        
        this.state = {
            data: data,
            errors: errors,
            validate: false,
            channelOptions: _.uniq(channelOptions)
        }
    }

    handleChange = ({name, value, errors}) => {
        if (['dataChoice'].includes(name) && value === 'open') {
            var newData = {
                ...this.state.data,
                dataChoice: value,
                hanfordChannel: 'GWOSC',
                livingstonChannel: 'GWOSC',
                virgoChannel: 'GWOSC'
            } 
        } else {
            var newData = {
                ...this.state.data,
                [name]: value,
            } 
        }

        // This change is to group the detector checkbox errors together
        if (['hanford', 'livingston', 'virgo'].includes(name)) {
            var newErrors = {
                ...this.state.errors,
                hanford: errors,
                livingston: errors,
                virgo: errors
            }
        } else {
            var newErrors = {
                ...this.state.errors,
                [name]: errors
            }
        }

        this.setState({
            data: newData,
            errors: newErrors
        })
    }

    handleAddition = (e, { value }) => {
        this.setState((prevState) => ({
          channelOptions: [value, ...prevState.channelOptions],
        }), () => {console.log(this.state)})
      }

    prevStep = () => {
        this.props.prevStep()
    }

    nextStep = () => {
        const notEmpty = (arr) => {
            return Boolean(arr && arr.length)
        }
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
        const forms = [
            {
                label: 'Type of Data', name: 'dataChoice', form: <Form.Select placeholder="Select Data Type" options={
                    [
                        {key: 'open', text: 'Open', value: 'open'},
                        {key: 'simulated', text: 'Simulated', value: 'simulated'}
                    ]
                }/>
            },
            {label: 'Detectors', name: 'hanford', form: <Form.Checkbox label="Hanford"/>, errFunc: checkForErrors(noneFalse([this.state.data.livingston, this.state.data.virgo]))},
            {label: null, name: 'livingston', form: <Form.Checkbox label="Livingston"/>, errFunc: checkForErrors(noneFalse([this.state.data.hanford, this.state.data.virgo]))},
            {label: null, name: 'virgo', form: <Form.Checkbox label="Virgo"/>, errFunc: checkForErrors(noneFalse([this.state.data.hanford, this.state.data.livingston]))},
            {
                label: 'Signal Duration (s)',
                name: 'signalDuration',
                form: <Form.Select placeholder="Select Signal Duration" options={
                    [
                        {key: '4', text: '4', value: '4'},
                        {key: '8', text: '8', value: '8'},
                        {key: '16', text: '16', value: '16'},
                        {key: '32', text: '32', value: '32'},
                        {key: '64', text: '64', value: '64'},
                        {key: '128', text: '128', value: '128'}
                    ]
                }/>
            },
            {
                label: 'Sampling Frequency (Hz)',
                name: 'samplingFrequency',
                form: <Form.Select placeholder="Select Sampling Frequency" options={
                    [
                        {key: '512', text: '512', value: '512'},
                        {key: '1024', text: '1024', value: '1024'},
                        {key: '2048', text: '2048', value: '2048'},
                        {key: '4096', text: '4096', value: '4096'},
                        {key: '8192', text: '8192', value: '8192'},
                        {key: '16384', text: '16384', value: '16384'},
                    ]
                }/>
            },
            {
                label: 'Trigger Time',
                name: 'triggerTime',
                form: <Form.Input placeholder='2.1'/>,
                errFunc: checkForErrors(isNumber, notEmpty)
            }
        ];

        Enumerable.from(['hanford', 'livingston', 'virgo']).forEach((e, i) => {
           if (this.state.data[e]) {
               forms.push(
                    {
                        label: e[0].toUpperCase() + e.slice(1) + ': Minimum Frequency (Hz)',
                        name: e + 'MinimumFrequency',
                        form: <Form.Input placeholder=''/>,
                        errFunc: checkForErrors(isNumber, notEmpty)
                    },
                    {
                        label: e[0].toUpperCase() + e.slice(1) + ': Maximum Frequency (Hz)',
                        name: e + 'MaximumFrequency',
                        form: <Form.Input placeholder=''/>,
                        errFunc: checkForErrors(isNumber, notEmpty)
                    },
                    {
                        label: e[0].toUpperCase() + e.slice(1) + ': Channel',
                        name: e + 'Channel',
                        form: <Form.Field 
                            control={Select} 
                            search 
                            allowAdditions 
                            onAddItem={this.handleAddition} 
                            placeholder="Select Channel"
                            options={
                                    // Create options from list of values, excluding some of the values
                                _.without(this.state.channelOptions, e==='virgo' ? 'GDS-CALIB_STRAIN' : 'Hrec_hoft_16384Hz').map(value => ({key: value, text: value, value: value}))
                            }
                            disabled={this.state.data.dataChoice==='open'}
                        />,
                        errFunc: checkForErrors(notEmpty)
                    }
               )
           }
        });

        const {data, errors} = this.state;
        return (
            <React.Fragment>
                <BaseForm data={data} errors={errors} forms={forms} onChange={this.handleChange}
                          validate={this.state.validate}/>
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
            triggerTime
            hanfordMinimumFrequency
            hanfordMaximumFrequency
            hanfordChannel
            livingstonMinimumFrequency
            livingstonMaximumFrequency
            livingstonChannel
            virgoMinimumFrequency
            virgoMaximumFrequency
            virgoChannel
        }
    `
});