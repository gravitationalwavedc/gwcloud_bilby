import React from "react";
import {FormController, FormField} from "./Forms";
import {Form, Grid, Button, Select} from "semantic-ui-react";
import {checkForErrors, isNumber, notEmpty, noneFalse} from "../../Utils/errors";
import _ from "lodash";

import {graphql, createFragmentContainer} from "react-relay";
import * as Enumerable from "linq";

class DataForm extends React.Component {
    constructor(props) {
        super(props);
        this.formController = React.createRef();

        const channelOptions = [
            'GWOSC',
            'GDS-CALIB_STRAIN',
            'Hrec_hoft_16384Hz',
        ]
        
        this.state = {
            channelOptions: _.uniq(channelOptions)
        }
    }

    handleAddition = (e, { value }) => {
        this.setState((prevState) => ({
          channelOptions: [value, ...prevState.channelOptions],
        }))
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
                errFunc: checkForErrors(noneFalse([values.livingston, values.virgo])),
                linkedErrors: {
                    livingston: (val) => checkForErrors(noneFalse([val, values.virgo])),
                    virgo: (val) => checkForErrors(noneFalse([val, values.livingston]))
                }
            },

            {
                label: null,
                name: 'livingston',
                form: <Form.Checkbox label="Livingston"/>,
                errFunc: checkForErrors(noneFalse([values.hanford, values.virgo])),
                linkedErrors: {
                    hanford: (val) => checkForErrors(noneFalse([val, values.virgo])),
                    virgo: (val) => checkForErrors(noneFalse([val, values.livingston]))
                }
            },

            {
                label: null,
                name: 'virgo',
                form: <Form.Checkbox label="Virgo"/>,
                errFunc: checkForErrors(noneFalse([values.hanford, values.livingston])),
                linkedErrors: {
                    hanford: (val) => checkForErrors(noneFalse([values.livingston, val])),
                    livingston: (val) => checkForErrors(noneFalse([values.hanford, val]))
                }
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
                errFunc: checkForErrors(isNumber, notEmpty)
            },
        ]
        

        Enumerable.from(['hanford', 'livingston', 'virgo']).forEach((name) => {
            forms.push(
                {
                    label: name[0].toUpperCase() + name.slice(1) + ': Minimum Frequency (Hz)',
                    name: name + 'MinimumFrequency',
                    form: <Form.Input placeholder=''/>,
                    errFunc: checkForErrors(isNumber, notEmpty),
                    visible: values[name]
                },

                {
                    label: name[0].toUpperCase() + name.slice(1) + ': Maximum Frequency (Hz)',
                    name: name + 'MaximumFrequency',
                    form: <Form.Input placeholder=''/>,
                    errFunc: checkForErrors(isNumber, notEmpty),
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
                    errFunc: checkForErrors(notEmpty),
                    visible: values[name]

                }
            )
        })

        return forms
    }

    render() {
        var initialData = {
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