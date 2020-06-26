import React from "react";
import {Form, Select} from "semantic-ui-react";
import BaseForm from "./BaseForm";
import {checkForErrors, isANumber, isNotEmpty, hasNoneFalse} from "../../Utils/errors";
import _ from "lodash";

import {graphql, createFragmentContainer} from "react-relay";
import * as Enumerable from "linq";

class DataForm extends React.Component {
    constructor(props) {
        super(props);

        this.initialData = {
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

        this.initialData = (this.props.data !== null) ? this.props.data : this.initialData
        this.initialData = (this.props.state !== null) ? this.props.state : this.initialData

        const channelOptions = [
            'GWOSC',
            'GDS-CALIB_STRAIN',
            'Hrec_hoft_16384Hz',
            this.initialData.hanfordChannel,
            this.initialData.livingstonChannel, 
            this.initialData.virgoChannel,
        ]
        
        this.state = {
            channelOptions: _.uniq(channelOptions),
        }
    }

    handleAddition = (e, { value }) => {
        this.setState((prevState) => ({
          channelOptions: [value, ...prevState.channelOptions],
        }))
    }

    setForms = (values) => {
        const forms = [
            {
                label: 'Type of Data',
                name: 'dataChoice',
                form: <Form.Select placeholder="Select Data Type" options={
                    [
                        {key: 'open', text: 'Open', value: 'open'},
                        {key: 'simulated', text: 'Simulated', value: 'simulated'}
                    ]
                }/>,
                valFunc: (val) => val === 'open' ? {hanfordChannel: 'GWOSC', livingstonChannel: 'GWOSC', virgoChannel: 'GWOSC'} : {},
            },

            {
                label: 'Detectors',
                name: 'hanford',
                form: <Form.Checkbox label="Hanford"/>,
                errFunc: checkForErrors(hasNoneFalse([values.livingston, values.virgo])),
                linkedErrors: {
                    livingston: (val) => checkForErrors(hasNoneFalse([val, values.virgo])),
                    virgo: (val) => checkForErrors(hasNoneFalse([val, values.livingston]))
                }
            },

            {
                label: null,
                name: 'livingston',
                form: <Form.Checkbox label="Livingston"/>,
                errFunc: checkForErrors(hasNoneFalse([values.hanford, values.virgo])),
                linkedErrors: {
                    hanford: (val) => checkForErrors(hasNoneFalse([val, values.virgo])),
                    virgo: (val) => checkForErrors(hasNoneFalse([val, values.livingston]))
                },
                required: false
            },
            
            {
                label: null,
                name: 'virgo',
                form: <Form.Checkbox label="Virgo"/>,
                errFunc: checkForErrors(hasNoneFalse([values.hanford, values.livingston])),
                linkedErrors: {
                    hanford: (val) => checkForErrors(hasNoneFalse([values.livingston, val])),
                    livingston: (val) => checkForErrors(hasNoneFalse([values.hanford, val]))
                },
                required: false
            },

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
                errFunc: checkForErrors(isANumber, isNotEmpty)
            },
        ]
        

        Enumerable.from(['hanford', 'livingston', 'virgo']).forEach((name) => {
            forms.push(
                {
                    label: name[0].toUpperCase() + name.slice(1) + ': Minimum Frequency (Hz)',
                    name: name + 'MinimumFrequency',
                    form: <Form.Input placeholder=''/>,
                    errFunc: checkForErrors(isANumber, isNotEmpty),
                    visible: values[name]
                },

                {
                    label: name[0].toUpperCase() + name.slice(1) + ': Maximum Frequency (Hz)',
                    name: name + 'MaximumFrequency',
                    form: <Form.Input placeholder=''/>,
                    errFunc: checkForErrors(isANumber, isNotEmpty),
                    visible: values[name]
                },
                
                {
                    label: name[0].toUpperCase() + name.slice(1) + ': Channel',
                    name: name + 'Channel',
                    form: <Form.Field 
                        control={Select} 
                        search 
                        allowAdditions 
                        onAddItem={this.handleAddition} 
                        placeholder="Select Channel"
                        options={
                                // Create options from list of values, excluding some of the values
                            _.without(this.state.channelOptions, name==='virgo' ? 'GDS-CALIB_STRAIN' : 'Hrec_hoft_16384Hz').map(value => ({key: value, text: value, value: value}))
                        }
                        disabled={values.dataChoice==='open'}
                    />,
                    errFunc: checkForErrors(isNotEmpty),
                    visible: values[name]

                }
            )
        })

        return forms
    }

    render() {
        return (
            <BaseForm 
                initialData={this.initialData}
                setForms={this.setForms}
                prevStep={this.props.prevStep}
                nextStep={this.props.nextStep}
                updateParentState={this.props.updateParentState}
            />
        )
    }
}

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