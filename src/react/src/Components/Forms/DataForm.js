import React, { useState } from "react";
import BaseForm from "./BaseForm";
import {isLargerThan, isANumber, isNotEmpty, hasNoneFalse, createValidationFunction, isLongerThan, isValidJobName} from "../../Utils/errors";
import _ from "lodash";

import {graphql, createFragmentContainer} from "react-relay";
import { mergeUnlessNull } from "../../Utils/utilMethods";
import { SelectField, CheckboxField, InputField, FormSegment } from "./Forms";
import { Segment, Grid, Divider, Header } from "semantic-ui-react";

function DataForm(props) {
    const formProps = {
        initialValues: mergeUnlessNull(
            {
                start: {
                    name: "",
                    description: "",
                    private: false
                },
                dataChoice: 'open',
                hanford: false,
                livingston: false,
                virgo: false,
                signalDuration: '4',
                samplingFrequency: '16384',
                triggerTime: '1126259462.391',
                hanfordMinimumFrequency: '20',
                hanfordMaximumFrequency: '1024',
                hanfordChannel: 'GWOSC',
                livingstonMinimumFrequency: '20',
                livingstonMaximumFrequency: '1024',
                livingstonChannel: 'GWOSC',
                virgoMinimumFrequency: '20',
                virgoMaximumFrequency: '1024',
                virgoChannel: 'GWOSC'
            },
            props.data === null ? null : {...props.data.data, start: props.data.start},
            props.state
        ),
        onSubmit: (values) => {
            const {start, ...data} = values
            props.updateParentState('start')(start)
            props.updateParentState('data')(data)
        },
        validate: (values) => createValidationFunction(
            {
                "start.name": [isLongerThan(5), isValidJobName],
                hanford: [hasNoneFalse([values.livingston, values.virgo])],
                livingston: [hasNoneFalse([values.hanford, values.virgo])],
                virgo: [hasNoneFalse([values.hanford, values.livingston])],
                triggerTime: [isANumber, isNotEmpty],
                hanfordMinimumFrequency: [isANumber, isNotEmpty],
                hanfordMaximumFrequency: [isLargerThan(values.hanfordMinimumFrequency, 'the minimum frequency'), isANumber, isNotEmpty],
                hanfordChannel: [isNotEmpty],
                livingstonMinimumFrequency: [isANumber, isNotEmpty],
                livingstonMaximumFrequency: [isLargerThan(values.livingstonMinimumFrequency, 'the minimum frequency'), isANumber, isNotEmpty],
                livingstonChannel: [isNotEmpty],
                virgoMinimumFrequency: [isANumber, isNotEmpty],
                virgoMaximumFrequency: [isLargerThan(values.virgoMinimumFrequency, 'the minimum frequency'), isANumber, isNotEmpty],
                virgoChannel: [isNotEmpty]
            },
            values
        ),
        linkedErrors: {
            hanford: ['livingston', 'virgo'],
            livingston: ['hanford', 'virgo'],
            virgo: ['hanford', 'livingston'],
        },
        linkedValues: (fieldName, fieldValue) => {
            switch (fieldName) {
                case 'dataChoice':
                    if (fieldValue === "open") {
                        return {hanfordChannel: 'GWOSC', livingstonChannel: 'GWOSC', virgoChannel: 'GWOSC'}
                    }
                    break;
                default:
                    break;
            }
    
        }
    }

    const [channelOptions, setChannelOptions] = useState(_.uniq(
        [
            'GWOSC',
            'GDS-CALIB_STRAIN',
            'Hrec_hoft_16384Hz',
            formProps.initialValues.hanfordChannel,
            formProps.initialValues.livingstonChannel, 
            formProps.initialValues.virgoChannel,
        ]
    ))

    const handleAddition = (e, { value }) => {
        setChannelOptions(prevChannelOptions => [value, ...prevChannelOptions])
    }

    function setForms(values) {
        const forms = {
            dataChoice: <SelectField label="Type of Data" name="dataChoice" placeholder="Select Data Type" options={
                [
                    {key: 'open', text: 'Open', value: 'open'},
                    {key: 'simulated', text: 'Simulated', value: 'simulated'}
                ]
            }/>,
            hanford: <CheckboxField label="Hanford" name="hanford" toggle/>,
            livingston: <CheckboxField label="Livingston" name="livingston" toggle/>,
            virgo: <CheckboxField label="Virgo" name="virgo" toggle/>,
            signalDuration: <SelectField label="Signal Duration (s)" name="signalDuration" placeholder="Select Signal Duration" options={
                    [
                        {key: '4', text: '4', value: '4'},
                        {key: '8', text: '8', value: '8'},
                        {key: '16', text: '16', value: '16'},
                        {key: '32', text: '32', value: '32'},
                        {key: '64', text: '64', value: '64'},
                        {key: '128', text: '128', value: '128'}
                    ]
            }/>,
            samplingFrequency: <SelectField label="Sampling Frequency (Hz)" name="samplingFrequency" placeholder="Select Sampling Frequency" options={
                [
                    {key: '512', text: '512', value: '512'},
                    {key: '1024', text: '1024', value: '1024'},
                    {key: '2048', text: '2048', value: '2048'},
                    {key: '4096', text: '4096', value: '4096'},
                    {key: '8192', text: '8192', value: '8192'},
                    {key: '16384', text: '16384', value: '16384'},
                ]
            }/>,
            triggerTime: <InputField label="Trigger Time (GPS Time)" name="triggerTime" />,
            hanfordMinimumFrequency: <InputField label="Hanford Minimum Frequency (Hz)" name="hanfordMinimumFrequency" key="hanfordMinimumFrequency"/>,
            hanfordMaximumFrequency: <InputField label="Hanford Maximum Frequency (Hz)" name="hanfordMaximumFrequency" key="hanfordMaximumFrequency"/>,
            hanfordChannel: <SelectField label="Hanford Channel" name="hanfordChannel" key="hanfordChannel"
                search 
                allowAdditions 
                onAddItem={handleAddition} 
                placeholder="Select Channel"
                options={
                        // Create options from list of values, excluding some of the values
                    _.without(channelOptions, 'Hrec_hoft_16384Hz').map(value => ({key: value, text: value, value: value}))
                }
                disabled={values.dataChoice==='simulated'}/>,
            livingstonMinimumFrequency: <InputField label="Livingston Minimum Frequency (Hz)" name="livingstonMinimumFrequency" key="livingstonMinimumFrequency"/>,
            livingstonMaximumFrequency: <InputField label="Livingston Maximum Frequency (Hz)" name="livingstonMaximumFrequency" key="livingstonMaximumFrequency"/>,
            livingstonChannel: <SelectField label="Livingston Channel" name="livingstonChannel" key="livingstonChannel"
                search 
                allowAdditions 
                onAddItem={handleAddition} 
                placeholder="Select Channel"
                options={
                        // Create options from list of values, excluding some of the values
                    _.without(channelOptions, 'Hrec_hoft_16384Hz').map(value => ({key: value, text: value, value: value}))
                }
                disabled={values.dataChoice==='simulated'}/>,
            virgoMinimumFrequency: <InputField label="Virgo Minimum Frequency (Hz)" name="virgoMinimumFrequency" key="virgoMinimumFrequency"/>,
            virgoMaximumFrequency: <InputField label="Virgo Maximum Frequency (Hz)" name="virgoMaximumFrequency" key="virgoMaximumFrequency"/>,
            virgoChannel: <SelectField label="Virgo Channel" name="virgoChannel" key="virgoChannel"
                search 
                allowAdditions 
                onAddItem={handleAddition} 
                placeholder="Select Channel"
                options={
                        // Create options from list of values, excluding some of the values
                    _.without(channelOptions, 'GDS-CALIB_STRAIN').map(value => ({key: value, text: value, value: value}))
                }
                disabled={values.dataChoice==='simulated'}/>
        }

        return (
            <React.Fragment>
                <FormSegment header="Data">
                    <Grid.Row columns={2}>
                        <Grid.Column>
                            {forms.dataChoice}
                            {forms.samplingFrequency}
                        </Grid.Column>
                        <Grid.Column>
                            {forms.triggerTime}
                            {forms.signalDuration}
                        </Grid.Column>
                    </Grid.Row>
                </FormSegment>
                <Segment basic as={Grid} columns='equal'>
                    <Grid.Row>
                        <Grid.Column>
                            <Segment color={values.hanford ? "black" : null} basic={!values.hanford}>
                                <Header as={Segment} basic textAlign="center">
                                    {forms.hanford}
                                    {values.hanford ? 'Activated' : 'Deactivated'}
                                </Header>
                                <Divider/>
                                {values.hanford && [forms.hanfordChannel, forms.hanfordMinimumFrequency, forms.hanfordMaximumFrequency]}
                            </Segment>
                        </Grid.Column>
                        <Grid.Column>
                            <Segment color={values.livingston ? "black" : null} basic={!values.livingston}>
                                <Header as={Segment} basic textAlign="center">
                                    {forms.livingston}
                                    {values.livingston ? 'Activated' : 'Deactivated'}
                                </Header>
                                <Divider/>
                                {values.livingston && [forms.livingstonChannel, forms.livingstonMinimumFrequency, forms.livingstonMaximumFrequency]}
                            </Segment>
                        </Grid.Column>
                        <Grid.Column>
                            <Segment color={values.virgo ? "black" : null} basic={!values.virgo}>
                                <Header as={Segment} basic textAlign="center">
                                    {forms.virgo}
                                    {values.virgo ? 'Activated' : 'Deactivated'}
                                </Header>
                                <Divider/>
                                {values.virgo && [forms.virgoChannel, forms.virgoMinimumFrequency, forms.virgoMaximumFrequency]}
                            </Segment>
                        </Grid.Column>
                    </Grid.Row>
                </Segment>
            </React.Fragment>
        )
    }

    return <BaseForm formProps={formProps} setForms={setForms}/>
}

export default createFragmentContainer(DataForm, {
    data: graphql`
        fragment DataForm_data on BilbyJobNode {
            data {
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
            start {
                name
                description
                private
            }
        }
    `
});